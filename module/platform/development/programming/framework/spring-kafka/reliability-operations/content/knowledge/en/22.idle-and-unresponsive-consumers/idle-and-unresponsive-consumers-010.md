# Consumer stuck in poll

## 1. Context and goal

In Spring Kafka, a listener container manages one or more `KafkaConsumer` instances. Consumers call **`poll()`** to fetch records from brokers, pass them to **`@KafkaListener`**, handle acknowledgments/offset commits, and repeat. A healthy poll loop either returns data or returns an empty list when the topic has no data.

An abnormal situation occurs when **`poll()` fails to return within a reasonable time**. At that point the application receives no more records, cannot detect idle state normally, and consumer lag can grow. This situation differs from a listener processing records slowly or a topic genuinely having no messages.

Spring Kafka provides **`NonResponsiveConsumerEvent`** to monitor consumers showing signs of being unresponsive in poll. This lesson explains the detection mechanism, timeout configuration, how to distinguish it from idle/slow processing, and production remediation without creating restart loops.

~~~text
KafkaMessageListenerContainer
       |
       v
Consumer thread
       |
       v
KafkaConsumer.poll()
       |
       +-- Returns records ---> @KafkaListener ---> commit/ack ---> next poll
       |
       +-- Returns empty -----> idle tracking ------> next poll
       |
       +-- Fails to return as expected
                  |
                  v
           Monitor scheduler
                  |
                  v
         NonResponsiveConsumerEvent
                  |
                  v
          Log/metric/investigate
                  |
                  v
         Controlled recovery
~~~

A `NonResponsiveConsumerEvent` is a **signal to investigate**, not conclusive proof that the Kafka broker is dead, the JVM is deadlocked, or a single restart will fix the problem.

## 2. How does the poll loop work?

A typical `KafkaMessageListenerContainer` performs these steps:

1. Create `KafkaConsumer` from `ConsumerFactory`.
2. Subscribe to topics or use configured assignments.
3. Join the consumer group and receive partition assignments.
4. Call `KafkaConsumer.poll` with the configured wait timeout.
5. When poll returns records, invoke the record listener or batch listener.
6. When processing finishes, commit/ack per `AckMode` and error handler.
7. Call the next poll while handling pauses, rebalances, and lifecycle.
8. When the container stops, close the consumer and release resources.

**`pollTimeout`** is the timeout passed into one poll call, not a limit on the entire loop iteration. A poll can return instantly while the listener spends minutes processing hundreds of records.

~~~text
poll()
   |
   v
records/empty
   |
   v
listener or idle logic
   |
   v
commit/error handling
   |
   v
next poll()
~~~

If poll does not return, subsequent steps in the loop have not executed yet. If the listener takes too long, poll already returned yet the loop cannot get back to the next poll. These two problems must be separated during diagnosis.

## 3. Distinguishing idle, non-responsive, and slow processing

| Symptom | Description | Key signal |
|---|---|---|
| **Idle** | Poll is working; no records delivered to listener | `ListenerContainerIdleEvent` |
| **Non-responsive** | Consumer shows signs of failing to progress past poll in expected time | `NonResponsiveConsumerEvent` |
| **Long processing** | Poll returned records, yet listener/callback holds the thread too long | Processing duration, thread dump, `max.poll.interval.ms` |
| **Paused** | Container intentionally pauses delivery per pause policy | `ConsumerPausedEvent`, pause state |
| **Stopped** | Consumer lifecycle has terminated | `ConsumerStoppedEvent`/`ContainerStoppedEvent` |
| **Unassigned** | Consumer has no partitions to read | Group/partition assignment |

You cannot conclude poll is stuck merely because no messages arrive. The topic may be empty, no partitions may be assigned, or records may be waiting on an upstream transaction to commit.

### 3.1. Consumer idle is a normal situation

A settlement topic may only have a few records per hour. A consumer polling steadily yet seeing zero records for 10 minutes can still be completely healthy.

If `idleEventInterval` is configured, Spring Kafka can emit `ListenerContainerIdleEvent`. This event indicates **no records were received during the idle interval**, not that poll is blocked.

### 3.2. Why doesn't non-responsive emit like idle?

`ListenerContainerIdleEvent` depends on the poll loop getting a chance to update idle state. If poll never exits, the container cannot continue the loop to emit idle events normally. Hence Spring Kafka runs a separate monitor that emits `NonResponsiveConsumerEvent` when poll exceeds its threshold.

~~~text
A. Empty topic yet healthy poll:

poll --> empty --> poll --> empty --> poll --> empty
                    |
                    v
            ListenerContainerIdleEvent

B. Poll does not return:

poll -----------------------------------> has not returned
          |
          v
    Independent monitor
          |
          v
    NonResponsiveConsumerEvent
~~~

## 4. NonResponsiveConsumerEvent in Spring Kafka

Class:

~~~java
org.springframework.kafka.event.NonResponsiveConsumerEvent
~~~

This is a **Spring application event** published by the listener container, not a Kafka record in a topic.

Useful properties:

| API | Meaning |
|---|---|
| **`getListenerId()`** | ID of the listener/container emitting the event |
| **`getTimeSinceLastPoll()`** | Elapsed time since the last poll, in milliseconds |
| **`getTopicPartitions()`** | Set of topic-partitions associated with the consumer |
| **`getSource()`** | Container emitting the event |
| **`getContainer()`** | Associated container, possibly parent when source is a child |
| **`getConsumer()`** | Reference to Kafka `Consumer` when provided |

**`getTimeSinceLastPoll()`** is not consumer lag, pending record count, or single-record processing duration. It is a poll-timing metric tracked by the framework.

Example observer:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaPollObserver {

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.error(
            "Kafka consumer non-responsive: listener={}, ms={}, partitions={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll(),
            event.getTopicPartitions()
        );
    }
}
~~~

This handler only logs. Never run `consumer.poll()`, `consumer.seek()`, `consumer.commitSync()`, or direct asynchronous operations on `KafkaConsumer`.

## 5. Three parameters for detecting non-responsive consumers

Spring Kafka uses properties in **`ContainerProperties`**:

| Property | Common default | Unit | Role |
|---|---:|---|---|
| **`pollTimeout`** | 5000 | milliseconds | Wait timeout passed to `poll()` |
| **`noPollThreshold`** | 3.0 | multiplier | Threshold relative to `pollTimeout` |
| **`monitorInterval`** | 30 | seconds | Monitor check cadence for consumer threads |

Conceptual detection threshold:

~~~text
pollTimeout × noPollThreshold
~~~

Example:

~~~text
pollTimeout      = 5000 ms
noPollThreshold  = 3.0

Threshold        = 5000 × 3.0
                 = 15000 ms
                 = 15 seconds

monitorInterval  = 30 seconds
~~~

The monitor is not an absolute-precision timer. If poll duration crosses the threshold between two checks, the event fires on the next applicable monitor check.

### 5.1. Why must noPollThreshold be greater than 1?

Spring Kafka documentation recommends **`noPollThreshold > 1.0`** to avoid false alarms from race conditions around poll completion. With 1.0, a normal poll can appear to breach the threshold due to slight timing or scheduling variance.

Choose the threshold based on detection needs, actual `pollTimeout`, and runtime jitter, rather than shrinking it to the minimum possible value.

## 6. Configuring the monitor in Java

Example listener factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaMonitoringConfig {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            monitoredKafkaListenerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);

        var props = factory.getContainerProperties();
        props.setPollTimeout(5_000L);
        props.setNoPollThreshold(3.0f);
        props.setMonitorInterval(10);

        return factory;
    }
}
~~~

Listener pointing to the factory:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "monitoredKafkaListenerFactory"
)
public void consume(OrderCreated order) {
    fulfillmentService.processIdempotently(order);
}
~~~

In this example, the threshold corresponds to 15 seconds and the monitor checks every 10 seconds. This is monitoring configuration; **it does not automatically restart the container**.

### 6.1. An application with multiple factories

If `@KafkaListener` uses a different factory, monitor settings on the factory above will not affect that listener. Always identify the container factory actually bound to each endpoint.

When concurrency is high, each child consumer has its own poll thread and should be tracked by listener/container identity.

## 7. Combining with ListenerContainerIdleEvent

You can enable idle events alongside it to separate empty topics from abnormal polling:

~~~java
var props = factory.getContainerProperties();

props.setPollTimeout(5_000L);
props.setIdleEventInterval(60_000L);
props.setNoPollThreshold(3.0f);
props.setMonitorInterval(10);
~~~

An observer for both:

~~~java
@Component
public class ConsumerHealthEvents {

    @EventListener
    public void idle(ListenerContainerIdleEvent event) {
        log.info(
            "Listener idle: listener={}, idleMs={}",
            event.getListenerId(),
            event.getIdleTime()
        );
    }

    @EventListener
    public void nonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
            "Suspected blocked Kafka poll: listener={}, sinceLastPollMs={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll()
        );
    }

    @EventListener
    public void noLongerIdle(ListenerContainerNoLongerIdleEvent event) {
        log.info(
            "Listener receiving records after idle: {}",
            event.getListenerId()
        );
    }
}
~~~

**`ListenerContainerNoLongerIdleEvent`** fires when records resume after an idle phase in supported versions. It is not a special event guaranteeing a non-responsive condition was resolved.

## 8. Event listener thread safety

`KafkaConsumer` is **not thread-safe**, except for operations explicitly permitted from another thread by the Kafka API under specific rules, such as `wakeup()`.

Non-responsive detection runs via the monitor/scheduler; never assume the `NonResponsiveConsumerEvent` observer executes on the consumer poll thread. Spring's event multicaster may also be configured asynchronously.

Therefore, the observer should not:

- Call `consumer.poll()`, `seek()`, `commitSync()`, or `subscribe()`.
- Retain a consumer reference for use on another executor.
- Run heavy I/O that blocks the scheduler.
- Arbitrarily pause/resume the consumer from an improper thread.
- Restart the container directly inside the callback without inspecting lifecycle.
- Send sensitive record data to logging backends.

Restrict callbacks to logging, Micrometer metrics, and dispatching **investigation requests** to a dedicated coordinator.

## 9. Why might poll fail to return?

Hypotheses to distinguish:

| Root-cause group | Example | How to verify |
|---|---|---|
| Kafka client | Bug in a specific `kafka-clients` version | Stack trace, version, release notes |
| Broker/network | Unstable TCP, DNS, broker/coordinator outage | Client logs, broker metrics |
| Group coordination | Slow join group/rebalance or stalled callbacks | Rebalance events, thread dump |
| User callback | Blocked rebalance listener, deserializer, interceptor | Thread dump, callback duration |
| Listener processing | Prolonged HTTP/DB call after poll | Thread dump at listener, processing timer |
| JVM | GC pause, CPU starvation, lock contention | GC logs, CPU/throttling, thread dump |
| Shutdown race | Container stopping while thread hasn't exited | Lifecycle events, stop logs |

Not every cause in this table means `KafkaConsumer.poll` itself is blocked internally. Some simply **stretch the gap between poll calls**. Use thread dumps to classify accurately.

### 9.1. Broker down does not always cause a blocked poll

Modern Kafka clients include reconnect and timeout mechanisms. A broker outage can leave poll returning empty so the consumer keeps cycling through its loop. In older `kafka-clients` versions, Spring Kafka docs noted cases where poll could hang when brokers were unreachable.

Therefore, never assume "broker down = poll deadlock" without checking your client version and observed behavior.

## 10. Thread dumps: essential evidence

When `NonResponsiveConsumerEvent` repeats, capture a thread dump per operational procedure. Permitted JVM tooling can be used, such as:

~~~text
jcmd <PID> Thread.print -l
~~~

Do not run it indiscriminately in production without authorization or if it impacts workloads. Thread dumps can expose resource names and sensitive data requiring protection.

Match the consumer thread:

| Where is the thread parked? | Investigation direction |
|---|---|
| `KafkaConsumer.poll` or network client | Client, broker, coordinator, network |
| Deserializer/interceptor | Schema, validation, custom interceptor, or bug |
| `onPartitionsAssigned`/`onPartitionsRevoked` | Blocked rebalance callback |
| `@KafkaListener`/HTTP client | Slow processing, downstream timeout |
| `WAITING` on application lock | Deadlock/lock contention |
| GC/CPU pressure | JVM pause or pod throttling |

Multiple thread dumps spaced briefly apart reveal whether stacks are advancing or frozen. Avoid taking them at overly high frequency.

### 10.1. Distinguishing a blocked poll from a blocked listener

If the stack shows:

~~~text
org.apache.kafka.clients.consumer.KafkaConsumer.poll(...)
~~~

then the blocked-poll hypothesis has direct evidence.

If the stack shows:

~~~text
FulfillmentService.callExternalApi(...)
HttpClient.execute(...)
~~~

then poll likely returned records and the listener itself is blocked. In that case, fix downstream timeouts, batch sizing, and `max.poll.interval.ms` rather than merely changing `pollTimeout`.

## 11. pollTimeout is not max.poll.interval.ms

The two properties mean completely different things:

- **`pollTimeout`**: wait duration inside a single `KafkaConsumer.poll` call used by the container.
- **`max.poll.interval.ms`**: Kafka's limit on time between valid consumer polls within a consumer group.

Example:

~~~text
pollTimeout          = 5 seconds
max.poll.interval.ms = 300 seconds

poll() returns batch in 1 second
listener processes for 400 seconds
next poll()
~~~

In this example, poll is not stuck internally; **overly slow listener processing** can cause the consumer to breach `max.poll.interval.ms`, lose group membership, or trigger a rebalance.

Another fault:

~~~text
pollTimeout = 5 seconds
poll() has not returned after 40 seconds
monitor emits NonResponsiveConsumerEvent
~~~

That is much closer to poll failing to return.

| Setting | Layer | Purpose |
|---|---|---|
| `pollTimeout` | Spring Kafka container | Timeout passed to poll |
| `noPollThreshold` | Spring Kafka monitor | Alert threshold |
| `monitorInterval` | Spring Kafka monitor | Check cadence |
| `max.poll.interval.ms` | Kafka client/group | Liveness between polls |
| `session.timeout.ms` | Kafka group protocol | Session failure detection |
| `request.timeout.ms` | Kafka client | Request wait timeout |

Never raise `max.poll.interval.ms` indefinitely to mask deadlocks, and never shrink `pollTimeout` tiny just to spin the poll loop faster without measuring the cost.

## 12. Batch listeners lengthen gaps between polls

A batch listener processes many records:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "ordersBatchFactory"
)
public void consume(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (var record : records) {
        fulfillmentService.process(record.value());
    }
}
~~~

If a batch has 400 records at 50 ms each:

~~~text
400 × 50 ms = 20,000 ms = 20 seconds
~~~

Adding HTTP timeouts or DB locks can stretch the listener to several minutes.

Mitigations:

- Tune **`max.poll.records`**.
- Enforce DB/HTTP timeouts.
- Track p95/p99 batch processing duration.
- Cap retries/backoff.
- Size concurrency to partition count and downstream capacity.
- Never offload records to a thread pool and commit before side effects finish.

If thread dumps show a slow listener, raising `noPollThreshold` only reduces alerts without fixing the bottleneck.

## 13. Blocking rebalance callbacks

Consumers execute callbacks when partitions are assigned or revoked. If a callback runs a slow database scan:

~~~text
KafkaConsumer.poll
       |
       v
Rebalance
       |
       v
onPartitionsAssigned(...)
       |
       +-- DB query
       +-- Cache restore
       +-- HTTP dependency
       |
       v
poll loop delayed
~~~

Never perform unbounded I/O inside `ConsumerAwareRebalanceListener`.

If local state must be restored, add timeouts, protect ownership, and fence stale tasks so old owners cannot write state after partitions move away.

When `NonResponsiveConsumerEvent` appears near a rebalance, inspect stack traces before immediately blaming the Kafka broker.

## 14. Pause vs non-responsive

Spring Kafka can temporarily pause a consumer/container to shed load or wait for downstream recovery. While paused, the container must still maintain polling/liveness per its mechanism to preserve group membership.

| State | Meaning |
|---|---|
| RUNNING | Container is active |
| PAUSED | Container temporarily halted delivery per pause policy |
| NON-RESPONSIVE | Monitor detected abnormal poll progress |
| STOPPED | Consumer/container ended its lifecycle |

In supported versions, containers offer **`pollTimeoutWhilePaused`** for polling while paused.

An intentionally paused container can accumulate lag without being "stuck". Never restart solely because throughput dropped if pausing is the intended state.

## 15. monitorInterval and false positives

Suppose:

~~~text
pollTimeout      = 5000 ms
noPollThreshold  = 3.0
monitorInterval  = 10000 ms

Threshold       ~ 15 seconds
Monitor checks every 10 seconds
~~~

If a poll stalls right after a check, the event may only arrive on the subsequent cycle. If a JVM GC pause lasts 20 seconds, the monitor can observe more elapsed time than expected even with zero deadlocks in the Kafka client.

Therefore, avoid deciding to stop/restart on **a single event**. Watch persistence, thread dumps, broker health, and resource pressure.

Correlate with:

- GC pause / safepoint durations.
- CPU usage and CPU throttling.
- Thread contention.
- Network disconnects/reconnects.
- Kafka client request latency.
- Consumer lag.
- Rebalance and assignment changes.

## 16. Concurrency and child containers

With `concurrency=3`:

~~~text
ConcurrentMessageListenerContainer
       |
       +-- child #0 --> KafkaConsumer #0
       +-- child #1 --> KafkaConsumer #1
       +-- child #2 --> KafkaConsumer #2
~~~

Each child runs its own poll thread. One child emitting `NonResponsiveConsumerEvent` does not mean all consumers in the group are broken.

When investigating, tie the event to:

- Listener/child ID.
- Parent container.
- Topic partitions.
- Client ID and group ID.
- Pod/instance.
- Per-partition consumer lag.
- Health of sibling children.

Stopping the parent for one isolated event forces healthy children out of the group and causes unnecessary rebalances.

## 17. Recovery: stopping the container in a controlled way

`KafkaConsumer` exposes **`wakeup()`** to interrupt certain blocking operations from another thread per the Kafka API. Yet in Spring Kafka, the container owns the `KafkaConsumer` and its lifecycle.

If a seemingly stuck consumer must be stopped, operate on the **managed listener container**. Never call poll, commit, or swap consumer instances directly from an event callback.

A sound architecture:

~~~text
NonResponsiveConsumerEvent
          |
          v
Brief observer log/metric
          |
          v
Recovery coordinator
          |
          +-- Deduplicate by listener ID
          +-- Verify still non-responsive?
          +-- Verify context not shutting down?
          +-- Collect diagnostics
          +-- Check root cause
          |
          v
Stop container on management thread if needed
          |
          v
Wait for stop-complete
          |
          v
Restart with policy backoff
          |
          v
Verify poll/assignment/offset progress
~~~

Never call stop on an inappropriate thread or call start before stop completes. With parent concurrent containers, avoid mistakenly operating on a single child instance.

### 17.1. Example observer sending only an investigation signal

~~~java
@Component
public class NonResponsiveAlertObserver {

    private final KafkaRecoveryCoordinator coordinator;

    public NonResponsiveAlertObserver(
            KafkaRecoveryCoordinator coordinator) {
        this.coordinator = coordinator;
    }

    @EventListener
    public void nonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
            "Kafka poll may be blocked: id={}, millis={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll()
        );

        coordinator.requestInvestigation(event.getListenerId());
    }
}
~~~

**`KafkaRecoveryCoordinator`** is a custom application class in this example; Spring Kafka does not ship a built-in class with that name.

The coordinator should inspect lifecycle, apply debounce/backoff, cap restart attempts, and never restart while the Spring context is closing.

## 18. Restart loops are another operational failure

A dangerous implementation:

~~~java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    var container = registry.getListenerContainer("orders-listener");
    container.stop();
    container.start();
}
~~~

Never use this pattern in production because:

- Stop may not have completed when start is called.
- The event came from a child while the parent may still be running.
- The root cause remains unfixed.
- The monitor can emit multiple events for one incident.
- During shutdown, the observer might restart a container that was intentionally stopped.
- Mass restarts cause rebalance and connection storms.

If automation is genuinely required, enforce a **single-flight guard**, **restart budget**, **backoff/jitter**, **stop-complete callback**, and **evidence-based recovery**.

## 19. Offsets and duplicates after restart

If a consumer produced side effects without committing Kafka offsets before stopping, records can be redelivered.

~~~text
Committed offset = 100

Old consumer:
    offset 100 -> DB update OK
    offset 101 -> DB update OK
    offset 102 -> in progress
    consumer restarts before Kafka commit

New consumer:
    may re-read starting from offset 100
~~~

This is at-least-once delivery. Non-responsive recovery does not automatically bring exactly-once guarantees to databases or HTTP APIs.

Safeguards:

1. Producers generate a stable event ID.
2. Consumers persist the event ID in the same DB transaction as business side effects.
3. Database enforces a unique constraint against duplicates.
4. External APIs use idempotency keys where available.
5. Offset commits occur only after appropriate processing/recovery.
6. DLT/poison records follow a dedicated handling flow.

Example:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Do not rely solely on a pre-insert existence check due to race conditions; the unique constraint is the primary safeguard.

## 20. Kafka transactions and non-responsive consumers

In pure Kafka consume-transform-produce flows, transactional containers coordinate Kafka outputs and source consumer offsets inside a single transaction.

When a transaction aborts due to an error or shutdown before commit:

- Uncommitted Kafka outputs are not delivered to `read_committed` consumers.
- Input offsets do not commit in the aborted transaction.
- Input records can be redelivered.
- Non-Kafka side effects do not roll back automatically.

If recovery restarts a transactional producer, ensure transactional ID uniqueness across pods to prevent `ProducerFencedException`.

`NonResponsiveConsumerEvent` does not tell whether transactions committed or aborted. To check Kafka transaction status, inspect the transaction manager, broker logs, and outcome metrics separately.

## 21. Monitoring and metrics

| Signal | What to know |
|---|---|
| `NonResponsiveConsumerEvent` count | Alert frequency per listener/consumer |
| `timeSinceLastPoll` | How long polling failed to progress |
| `ListenerContainerIdleEvent` count | Is polling still active despite no records? |
| Listener processing duration | Is business code blocking? |
| Poll latency and request latency | Are Kafka client/brokers slow? |
| Consumer lag per partition | Which partitions are building backlog? |
| Records consumed rate | Has throughput stopped? |
| Rebalance count/duration | Is the group unstable? |
| Assigned partitions | Does the consumer still own partitions? |
| GC pauses / CPU throttling | Is JVM/node delaying the consumer thread? |
| Commit errors | Are offsets advancing per policy? |
| Restart attempts | Is a restart loop happening? |
| DLT/recovery failures | Are poison records stalling the pipeline? |

Exact metric names depend on `kafka-clients`, Spring Kafka, Micrometer, JMX exporters, and dashboards. Never assume all metrics exist out of the box.

### 21.1. Structured log

~~~text
event=non_responsive_consumer
listenerId=orders-listener-1
groupId=order-fulfillment
topicPartitions=orders.created-2,orders.created-3
timeSinceLastPollMs=37000
pollTimeoutMs=5000
noPollThreshold=3.0
monitorIntervalSeconds=10
action=investigate
~~~

Never log key/value payloads or secrets just to diagnose non-responsiveness. What matters are timing, consumer identity, and state.

## 22. Production runbook

1. Identify service/pod, listener ID, group ID, and partitions.
2. Record `NonResponsiveConsumerEvent` and `timeSinceLastPoll`.
3. Verify effective `pollTimeout`, `noPollThreshold`, and `monitorInterval`.
4. Check whether the container is RUNNING, PAUSED, STOPPING, or STOPPED.
5. Correlate with idle events and producer publish rates.
6. Inspect per-partition lag and last committed offset.
7. Capture an authorized thread dump to see whether the thread is in poll or listener.
8. Inspect Kafka client logs: disconnects, timeouts, coordinator, and rebalances.
9. Check broker health, DNS, networking, TLS, and ACLs.
10. Check GC pauses, CPU throttling, thread contention, and task executors.
11. If blocked in listener, inspect DB/HTTP timeouts, batch size, and retry/backoff.
12. If blocked in rebalance callback, inspect state restoration and external calls.
13. Determine whether the event spans multiple monitor cycles or was a single spike.
14. Never reset offsets or mass-restart before identifying the root cause.
15. If necessary, stop/restart the managed container from a separate coordination thread.
16. Wait for partition assignment and poll/processing resumption.
17. Verify offset commits and consumer lag dropping.
18. Verify idempotency for any redelivered records.
19. Document root cause, remediation, and recovery evidence.

**Never use `container.isRunning()` alone as incident closure criteria.** A running container can still lack partitions, remain paused, or fail to process records.

## 23. Integration testing: idle, blocked poll, and slow listener

Separate three independent test cases using a real Kafka broker or appropriate Embedded Kafka/Testcontainers.

### 23.1. Consumer idle

- Create a topic with zero records.
- Set a small `idleEventInterval` in test config.
- Start the listener and wait for assignment.
- Verify `ListenerContainerIdleEvent` appears.
- Send a record and verify the listener receives it.
- Where supported by version, verify `ListenerContainerNoLongerIdleEvent`.

The test proves an empty topic does not equal a stuck poll.

### 23.2. Non-responsive

- Configure small, bounded `pollTimeout`, `noPollThreshold`, and `monitorInterval`.
- Use a test-specific consumer wrapper or fault injection to induce a controlled poll delay.
- Collect `NonResponsiveConsumerEvent`.
- Verify listener ID and `timeSinceLastPoll`.
- Remove the fault injection and stop the container if needed.
- Verify cleanup leaves no blocked threads after the test ends.

Never design tests that block consumer threads forever or simply kill the broker assuming every `kafka-clients` version hangs identically.

### 23.3. Slow listener

- Send a sizable batch or simulate downstream latency with a timeout.
- Measure listener processing duration.
- Observe `max.poll.interval.ms` and rebalances.
- Capture a thread dump within test scope.
- Verify the stack sits inside business code when the listener is blocked.
- Try lowering batch size or adding timeouts and re-measure.

Tests prevent operations teams from misdiagnosing causes and tweaking the wrong poll settings.

## 24. Real-world example: Order Fulfillment

Order Fulfillment uses topic `orders.created` with eight partitions across two pods, each with `concurrency=2`. Factory:

~~~java
var props = factory.getContainerProperties();

props.setPollTimeout(5_000L);
props.setNoPollThreshold(3.0f);
props.setMonitorInterval(10);
props.setIdleEventInterval(60_000L);
~~~

One child emits:

~~~text
listenerId=orders-listener-1
timeSinceLastPollMs=42000
partitions=[orders.created-4, orders.created-5]
~~~

Operations response:

1. Check lag on P4/P5; other partitions keep advancing.
2. Inspect Kafka client logs and broker connection metrics.
3. Capture a thread dump from the affected pod.
4. If the thread is inside `network-client` poll code, check `kafka-clients` version, broker/coordinator, and networking.
5. If the thread is inside `FulfillmentService` calling an untimed API, fix timeouts and retry policies.
6. Correlate GC pauses, CPU throttling, and monitor interval.
7. When a container cannot recover, stop/restart with backoff and stop-complete—never directly inside the event callback.
8. After restart, verify group assignment, commits, and lag declining.
9. Verify event ID deduplication for potentially redelivered records.

Lesson from this case: **the event is only the starting point of investigation; root cause and post-recovery progress determine success**.

## 25. Mistakes to avoid

**"Seeing no records means poll is stuck."** False. The topic may be empty or the consumer paused.

**"Idle events and non-responsive events are the same."** False. One reflects no incoming records; the other warns of abnormal poll progress.

**"`NonResponsiveConsumerEvent` proves the Kafka broker is down."** False. Thread dumps and broker/network evidence are required.

**"No idle events means the consumer is healthy."** False. A poll that never returns prevents idle events from firing.

**"`pollTimeout` is `max.poll.interval.ms`."** False. The two limits operate at different layers.

**"`monitorInterval=10` guarantees the event arrives after exactly 10 seconds."** False. Both the threshold and scheduler affect timing.

**"`noPollThreshold=1.0` is more accurate."** Not recommended; Spring Kafka advises `>1.0` to avoid false positives.

**"When the event fires, call `KafkaConsumer.commitSync`."** Unsafe. `KafkaConsumer` is not thread-safe.

**"Stop then immediately start inside the event handler."** Can cause lifecycle races, especially with child containers.

**"Restarting the container creates no duplicates."** False. Uncommitted records can be redelivered.

**"Broker outages always cause blocked polls."** Incorrect; many `kafka-clients` versions handle reconnects/timeouts cleanly.

**"Raising `max.poll.interval.ms` fixes deadlocks."** False. That is a liveness setting, not a fix for blocked code.

## 26. Operational checklist

- [ ] Confirm listener/container ID and consumer group.
- [ ] Know effective `pollTimeout`, `noPollThreshold`, and `monitorInterval`.
- [ ] Ensure `noPollThreshold` is greater than `1.0`.
- [ ] Have a lightweight, thread-safe `NonResponsiveConsumerEvent` observer.
- [ ] Enable idle events if needed to distinguish empty topics.
- [ ] Never call `KafkaConsumer` methods from an arbitrary observer thread.
- [ ] Instrument consumer lag and partition assignment metrics.
- [ ] Have JVM GC, CPU, and thread dump diagnostics available.
- [ ] Enforce timeouts on DB/HTTP calls and bound batch processing.
- [ ] Never restart on a single isolated warning without corroborating evidence.
- [ ] Recovery coordinator uses single-flight guard, stop-complete, backoff, and budget.
- [ ] Never trigger restarts during application shutdown.
- [ ] Enforce idempotency for record redeliveries.
- [ ] Test differentiating idle, non-responsive, and slow listener processing.
- [ ] After recovery, verify throughput, assignments, and offset commits.

## 27. References

- Spring Kafka Reference — Application Events: https://docs.spring.io/spring-kafka/reference/kafka/events.html
- Spring Kafka Reference — Listener Container Properties: https://docs.spring.io/spring-kafka/reference/kafka/container-props.html
- Spring Kafka JavaDoc — NonResponsiveConsumerEvent: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/event/NonResponsiveConsumerEvent.html

When implementing, cross-check against your exact Spring Kafka and `kafka-clients` versions, especially if the application uses a custom `ConsumerFactory`, asynchronous event multicaster, or custom listener container lifecycle.

## 28. Key takeaways

**Consumer stuck in poll** refers to a Kafka consumer failing to meet expected poll progress. Spring Kafka uses **`NonResponsiveConsumerEvent`** to warn about it, using a threshold based on **`pollTimeout × noPollThreshold`** and a check cadence of **`monitorInterval`**. Common defaults are a 5-second `pollTimeout`, `noPollThreshold` of 3.0, and a 30-second `monitorInterval`.

Distinguish a non-returning poll from an idle topic, slow listener processing, paused containers, and stopped consumers. The event is only a signal; thread dumps, client logs, broker metrics, partition assignments, and consumer lag reveal the root cause.

During recovery, fix the root cause first, never manipulate `KafkaConsumer` from arbitrary threads, avoid restart loops, and ensure proper offset commits alongside idempotency for potential redeliveries. A system is only truly recovered when polling, processing, and commits all show real progress.
