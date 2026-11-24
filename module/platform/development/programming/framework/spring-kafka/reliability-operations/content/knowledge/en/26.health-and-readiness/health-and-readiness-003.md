# Consumer Thread Liveness

A Spring Kafka application can remain alive at the process level while its consumer thread has stopped making progress. HTTP endpoints still respond, the JVM still consumes CPU, and the overall health endpoint remains green, yet a `@KafkaListener` fails to invoke the next `poll()` and the consumer group begins falling behind. This is a class of failure that is hard to detect if you only check whether the process or container is running.

**Consumer thread liveness** is the ability of the consumer thread to continue executing the Kafka consumption loop, specifically returning to call `KafkaConsumer.poll()` within an appropriate timeframe. Spring Kafka provides a monitoring mechanism and the `NonResponsiveConsumerEvent` application event to report that a consumer has not polled within the configured threshold. This signal helps detect blocked listeners, thread starvation, deadlocks, or a dependent operation waiting for too long.

Consumer thread liveness differs from JVM/process liveness, differs from application readiness, and also differs from Kafka consumer group heartbeats. Proper diagnosis requires combining container state, poll progress, `max.poll.interval.ms`, heartbeat/session timeouts, thread dumps, lag, and business processing duration. A non-responsive event is a **signal to investigate**, not proof that Kafka brokers are broken or that the process must definitely restart.

## 1. What does the consumer thread do?

In the standard listener container model, Spring Kafka manages a Kafka consumer on a consumer thread. This thread repeatedly performs:

1. Calling `KafkaConsumer.poll()` to fetch records and keep the consumer group active.
2. Delivering records to the listener adapter or listener method.
3. Waiting for the listener to process according to configured record/batch, acknowledgment, and transaction semantics.
4. Completing the corresponding commit/recovery.
5. Returning to `poll()` to continue consuming.

Simple diagram:

~~~text
Consumer thread
      |
      v
  poll()
      |
      v
  records
      |
      v
@KafkaListener
      |
      +--> business logic
      +--> database / HTTP / cache
      +--> KafkaTemplate
      |
      v
ack / commit / recovery
      |
      v
  next poll()
~~~

If the listener takes too long or blocks, the consumer thread may fail to return to `poll()` on time. The Kafka client has heartbeat and group membership mechanisms, while Spring Kafka can observe the duration without a poll to detect a non-progressing consumer.

### 1.1. A live thread does not mean a progressing consumer

A Java thread can exist while being:

- `BLOCKED` waiting on a monitor lock.
- `WAITING` or `TIMED_WAITING` waiting on a future, semaphore, queue, or I/O.
- `RUNNABLE` but stuck in a non-terminating CPU loop.
- Waiting on a database connection pool or HTTP response.
- Starved because the executor cannot allocate threads.
- Waiting on a callback that only executes if that same thread keeps progressing.

Therefore, checking whether the thread exists or the process has not exited is insufficient. What matters is **whether the consumer returns to poll and processes data**.

### 1.2. Consumer thread liveness does not equal message throughput

A consumer may poll steadily while a topic has no records. In that case, the consumer is still responsive even though throughput is 0. Conversely, a consumer might just have received a batch and gotten stuck inside the listener; prior throughput may still look high even though poll progress has stopped.

Two questions must be measured separately:

- **Liveness/progress:** does the consumer continue polling within bounds?
- **Data progress:** does the consumer receive and complete records as expected?

## 2. Spring Kafka's NonResponsiveConsumerEvent

Spring Kafka provides the `NonResponsiveConsumerEvent` application event to report when a consumer fails to invoke or complete poll progress within the interval monitored by the container. This is a Spring Kafka-layer event, not a record sent from the broker and not necessarily an exception thrown by the listener method.

The event helps detect situations such as:

- A listener method waiting too long for an HTTP request.
- A database query or connection acquisition hanging.
- An application lock held indefinitely.
- The consumer thread blocked by synchronous code.
- Thread pool or JVM starvation.
- A bug in a callback or integration preventing the consumer from returning to the poll loop.

Upon receiving the event, the system can log, increment metrics, update readiness state, or trigger a controlled investigation/recovery workflow.

### 2.1. The event does not prove the thread is dead

The name "non-responsive" describes **the absence of poll progress within the monitoring threshold**. The thread may still be executing a method, waiting on network I/O, or holding/waiting for a lock. It is not necessarily in the `TERMINATED` state.

This is why you need to capture thread dumps and inspect stack frames instead of immediately restarting.

### 2.2. The event is not a Kafka broker error

A consumer can stop polling because application code is blocked while brokers are completely healthy. Conversely, a consumer can continue calling `poll()` while hitting repeated network/authorization errors. The two situations exhibit different symptoms and require inspecting Kafka client logs as well.

## 3. monitorInterval, noPollThreshold, and pollTimeout

The container has properties to monitor time without polling:

| Property | Role |
|---|---|
| `pollTimeout` | How long a single `poll()` can wait for data before returning |
| `monitorInterval` | How often the monitor checks consumer health |
| `noPollThreshold` | Multiplier used to determine a no-poll duration long enough to treat the consumer as non-responsive |

In Spring Kafka versions supporting this mechanism, the detection threshold is typically calculated from **poll timeout multiplied by the no-poll threshold**; the monitor task checks on `monitorInterval`. Thus, the event does not necessarily fire at the exact instant the threshold is crossed. Verify the calculation and defaults in the Javadoc of the Spring Kafka version you are deploying.

Illustrative example:

~~~text
pollTimeout      = 5 seconds
noPollThreshold  = 3.0
monitorInterval  = 10 seconds

No-poll evaluation threshold ≈ 5 × 3 = 15 seconds
Monitor checks every 10 seconds

The event can be emitted on the first monitor check
that detects the no-poll duration has exceeded the threshold.
~~~

This illustrates how to reason about the three parameters, not a guarantee that the event always fires at exact second 15. Poll scheduling, monitor scheduling, and version implementation affect the exact observation time.

### 3.1. Configuring ContainerProperties

Java example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    ContainerProperties properties =
            factory.getContainerProperties();

    properties.setPollTimeout(5_000L);
    properties.setMonitorInterval(10);
    properties.setNoPollThreshold(3.0);

    return factory;
}
~~~

The setters and data types for the monitor interval must match the Spring Kafka version in your project. This example shows where to configure them; do not copy values straight into production without comparing against actual processing times and the API in use.

### 3.2. Do not set the threshold below normal processing time

Suppose a listener normally processes a batch in 20 seconds while the non-responsive threshold is only 15 seconds. The system can emit events while the consumer is performing valid work.

Compute the threshold from:

- Processing duration p95/p99.
- Batch size and record count per poll.
- Database/HTTP call duration.
- Queue/lock wait time.
- Poll timeout.
- `max.poll.interval.ms` and group protocol.

Do not pick a threshold just to make events appear quickly; false positives will erode operations' trust in alerts.

## 4. Handling NonResponsiveConsumerEvent

Events can be received using Spring's `@EventListener`:

~~~java
@Component
public class ConsumerLivenessEvents {

    private static final Logger log =
            LoggerFactory.getLogger(ConsumerLivenessEvents.class);

    @EventListener
    public void onNonResponsive(
            NonResponsiveConsumerEvent event) {

        log.error(
                "Kafka consumer has not polled within the expected " +
                "interval: listener={}, timeSinceLastPollMs={}, partitions={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll(),
                event.getTopicPartitions());
    }
}
~~~

This example uses accessors commonly present on the event in corresponding Spring Kafka versions. Verify package names and method signatures in your project version's Javadoc. Do not assume every version exposes identical metadata or constructors.

The event can provide context such as listener ID, container, consumer, time since last poll, and partitions. Use only the fields actually present in your current API.

### 4.1. Event handlers should be lightweight

An event callback should:

- Write a short structured log.
- Increment a counter.
- Store timestamps/last-known state in a thread-safe structure.
- Signal a bounded health aggregator or alert pipeline.

Do not make long HTTP requests, run heavy database queries, sleep, or execute a restart sequence inside the callback. Events are published on lifecycle/container monitoring paths; heavy callbacks can slow down monitoring itself.

### 4.2. Never invoke KafkaConsumer directly from the event thread

The event may expose a consumer reference for diagnostics. However, `KafkaConsumer` is not thread-safe for arbitrary operations from another thread. Do not call `poll()`, `seek()`, `commitSync()`, or manipulate the consumer directly from the event listener.

Use Spring listener container management APIs and respect thread ownership. If a thread dump is needed, capture it from the JVM/process using administrative tools instead of touching the consumer.

## 5. Distinguishing types of liveness

The word "liveness" is often applied to different layers:

| Layer | Question | Example Signal |
|---|---|---|
| Process/JVM liveness | Is the JVM running and able to keep executing? | Process state, deadlock, JVM fatal error |
| Container lifecycle | Has the Spring listener container started and not stopped? | `isRunning()` |
| Consumer-thread progress | Does the consumer return to poll on time? | `NonResponsiveConsumerEvent` |
| Kafka group membership | Does the broker still view the consumer as a group member? | Heartbeat, session timeout, rebalance |
| Readiness | Is the instance capable of accepting more traffic/work? | Readiness probe and dependency policy |
| Business progress | Are events being processed successfully within SLO? | Success rate, oldest record age, lag |

Do not use a single health boolean to represent all of these concepts.

### 5.1. Container running does not mean consumer responsive

`MessageListenerContainer.isRunning()` reports container lifecycle state. The container can still report running while the consumer thread is blocked and has not polled again.

### 5.2. Consumer responsive does not mean the topic has data

A consumer can poll steadily without receiving records. If the topic is empty and the group has no lag, that can be a healthy state. Do not mark it unhealthy merely because throughput is 0.

### 5.3. Group membership differs from listener progress

Kafka uses heartbeats and group coordination to detect disconnected members or members no longer satisfying the protocol. A consumer thread can be blocked inside a listener while heartbeats remain active for a while, though `max.poll.interval.ms` still bounds the time between polls.

Therefore, the fact that the group has not rebalanced immediately does not prove the listener is still processing data.

## 6. max.poll.interval.ms and session.timeout.ms

Kafka consumers have distinct timeouts, each protecting a different aspect.

| Configuration | Meaning |
|---|---|
| `max.poll.interval.ms` | Time limit between poll calls in the consumer group protocol |
| `session.timeout.ms` | Threshold the broker waits for heartbeats before considering the member's session lost |
| `heartbeat.interval.ms` | Heartbeat frequency per the corresponding client/protocol configuration |
| `pollTimeout` | Time a single poll can wait for data inside the container |
| `monitorInterval` | Frequency of Spring monitor checks |
| `noPollThreshold` | Threshold multiplier for detecting stalled poll progress |

These parameters do not replace one another.

### 6.1. max.poll.interval.ms protects poll progress

If the consumer does not call `poll()` within `max.poll.interval.ms`, the Kafka group coordinator can treat the consumer as no longer making progress and trigger group departure/rebalancing per the protocol.

This is especially important when the listener method runs synchronously on the consumer thread. A business operation that blocks too long can delay the next poll past the deadline.

### 6.2. session.timeout.ms protects heartbeats

Session timeout focuses on the broker not receiving heartbeats within the configured window. In the classic consumer group protocol, heartbeats are handled by client background activity, yet poll progress remains bounded by `max.poll.interval.ms`. Details can differ with newer group protocols and Kafka client versions.

Do not increase `session.timeout.ms` to mask a blocked listener. Nor should you increase `max.poll.interval.ms` indefinitely, as that delays the group from detecting a stalled consumer.

### 6.3. Example of a blocked listener

~~~text
T0: consumer poll() receives a batch
T1: listener begins processing the batch
T2: downstream HTTP hangs
T3: consumer thread still waits on HTTP, does not poll again
T4: Spring monitor emits NonResponsiveConsumerEvent
T5: max.poll.interval.ms may be exceeded
T6: group coordinator handles the non-progressing member
~~~

Actual timing and order depend on timeouts, heartbeat protocol, monitor scheduling, and block duration. Do not treat the Spring event and Kafka's rebalance as simultaneous events.

## 7. Common causes of stalled consumer threads

### 7.1. Synchronous I/O without timeouts

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) {
    // HTTP client lacks an appropriate deadline.
    paymentClient.charge(event);
}
~~~

If downstream does not respond, the listener holds the consumer thread. Connect/read/call timeouts, bounded retries, and appropriate circuit breakers are needed.

### 7.2. Database connection pool exhaustion

The listener may wait to acquire a connection from the pool. If other transactions hold connections too long, the consumer thread cannot finish the listener and does not return to poll.

Monitor:

- Active/idle/pending connections.
- Connection acquisition timeout.
- Query duration.
- Transaction duration.
- Lock waits/deadlocks.

Increasing consumer concurrency when the DB pool is already exhausted can make the problem worse.

### 7.3. Lock contention or deadlock

A thread may sit in `BLOCKED` state waiting for a monitor, or multiple threads may wait on locks in a cycle. Capturing multiple thread dumps helps identify unchanging stack traces and lock owners.

### 7.4. Future.get()/join() without a deadline

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) throws Exception {
    downstreamClient.callAsync(event).get();
}
~~~

`get()` without a timeout can wait forever. Use an appropriate deadline and handle cancellation/retry according to semantics; the timeout must fit within both business processing time and the poll budget.

### 7.5. CPU loops or GC pressure

A listener may execute heavy computation, allocate large objects, or trigger long GC pauses. The thread is still running, but poll progress slows down.

Monitor CPU throttling, allocation rate, heap, GC pause duration, and processing latency.

### 7.6. Executor starvation

If consumer tasks share an executor with long-running tasks, consumers may fail to run or resume on the expected schedule. Separate pools for long-lived consumer tasks from other background/HTTP work, or size capacity for total actual concurrency.

## 8. Poll loop and record/batch processing time

For synchronous record listeners, the listener method is typically invoked while the container processes records returned from a poll. The processing time of records in one poll affects the interval until the next poll.

For example, a poll receives 100 records, each taking 200 ms:

~~~text
100 × 200 ms = 20,000 ms ≈ 20 seconds
~~~

This is simple multiplication. Actual time can differ due to parallel work, batch listeners, error handlers, backoff, database contention, and framework overhead.

If `max.poll.interval.ms` is only 15 seconds, a 20-second batch risks exceeding the limit. If using a batch listener, processing time for the entire batch must fit within an appropriate budget.

### 8.1. Reducing max.poll.records is not always the answer

Lowering `max.poll.records` can shrink batches and reduce per-poll processing time. However, it also increases poll/commit frequency and can reduce throughput due to overhead.

Measure:

- Actual batch size.
- Processing time per record/batch.
- Poll-to-poll interval.
- Commit latency.
- Consumer lag.

Then tune batch size and concurrency based on data.

### 8.2. Async listeners do not automatically solve liveness

Some listener styles returning futures or using async processing have specific semantics depending on Spring Kafka version and ack mode. Do not assume every asynchronous method frees the consumer thread immediately while still ensuring offsets are not committed prematurely.

When moving to async, verify:

- When is the listener considered complete?
- At what point are offsets acknowledged/committed?
- How do exceptions from workers return to the container?
- Can the consumer pull more records than the queue can hold?
- Is context/trace propagated across thread boundaries?

## 9. Thread dumps are the primary diagnostic tool

When `NonResponsiveConsumerEvent` occurs, a thread dump helps locate where the consumer thread is stuck.

On the JVM, you can use:

~~~bash
jcmd <pid> Thread.print
~~~

Or:

~~~bash
jstack <pid>
~~~

In containerized environments, run with appropriate permissions and the right PID inside the process namespace. Do not post fake PIDs or thread dump outputs containing sensitive information in public channels.

### 9.1. Capture multiple thread dumps

A single thread dump is a snapshot. Capturing two or three snapshots spaced a few seconds apart distinguishes:

- A thread progressing through stack frames.
- A thread waiting forever on the same network read.
- A thread stuck on a lock.
- A thread spinning in a CPU loop.
- A thread that has terminated.

Do not read `WAITING` alone and conclude deadlock; many healthy threads wait on queues/conditions.

### 9.2. Locating the consumer thread

Thread names depend on container type, concurrency, Spring Kafka version, and naming configuration. Search for names related to the listener/container or Kafka consumer, then verify actual stack frames rather than relying on a fixed prefix.

Stack traces can reveal:

- `KafkaConsumer.poll`: inside the poll loop.
- `SocketInputStream.read` or network client: waiting on I/O.
- `CompletableFuture.get`: waiting on async completion.
- JDBC driver/connection pool: waiting on database.
- Application service: executing business logic.
- `AbstractQueuedSynchronizer`/monitor: waiting on a lock/semaphore.

### 9.3. Thread dumps can contain sensitive data

Stack traces can include URLs, SQL, tenant names, internal class names, and values in local variables depending on tooling. Store and share according to security policies; never send full dumps over unprotected channels.

## 10. Recording NonResponsiveConsumerEvent and metrics

A lightweight listener can increment a counter and log time since last poll:

~~~java
@Component
public class ConsumerLivenessMonitor {

    private static final Logger log =
            LoggerFactory.getLogger(ConsumerLivenessMonitor.class);

    private final Counter nonResponsiveEvents;

    public ConsumerLivenessMonitor(MeterRegistry registry) {
        this.nonResponsiveEvents = Counter.builder(
                "app.kafka.consumer.non_responsive.events")
                .description("Non-responsive Kafka consumer events")
                .register(registry);
    }

    @EventListener
    public void onNonResponsive(
            NonResponsiveConsumerEvent event) {

        nonResponsiveEvents.increment();

        log.error(
                "Kafka consumer poll progress stalled: listener={}, " +
                "timeSinceLastPollMs={}, partitions={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll(),
                event.getTopicPartitions());
    }
}
~~~

This example uses Micrometer and event accessors from an appropriate Spring Kafka version. This metric is application-defined, not a default Spring Kafka metric name.

### 10.1. Do not create metric tags from offsets or exception messages

Metric tags should have low cardinality, for example:

- service.
- environment.
- listener ID (finite set).
- standardized failure category.

Do not put dynamic topic-partition lists, offsets, event IDs, trace IDs, or verbatim exception messages into metric labels. Use structured logs/traces for per-incident details.

### 10.2. Deduplicating events

If a consumer remains blocked, the monitor can keep emitting events across check cycles. Do not create a new page for every event.

You can track:

- Listener/container ID.
- Instance/pod.
- First non-responsive timestamp.
- Most recent timestamp.
- Current incident state.
- Event count within the same incident.
- Timestamp when poll progress recovered.

Open an incident once when transitioning from healthy to stalled; update the open incident on repeated events; close it once poll progress is confirmed to have resumed.

## 11. What should readiness and liveness probes reflect?

In Kubernetes or similar orchestration environments, there are typically two probe types:

- **Liveness probe:** the process needs to restart because it cannot recover on its own.
- **Readiness probe:** whether the instance should receive more traffic/new work.

A non-responsive consumer thread does not automatically mean the entire JVM must restart immediately. Readiness may need to transition to false or degraded while liveness stays true to avoid a restart loop.

### 11.1. Liveness probes should not depend directly on Kafka brokers

If the liveness endpoint fails whenever Kafka brokers are temporarily unavailable, the orchestrator may restart all pods simultaneously, causing a rebalance storm right as brokers recover.

Liveness should reflect the ability of the process/JVM itself to progress and unrecoverable failure states. Dependency health usually belongs in readiness or dependency-specific alerts.

### 11.2. Readiness for consumer workers

If an application is purely a Kafka worker serving no HTTP traffic, readiness can still report operational state to the orchestrator/monitoring. Define:

- Which consumers are mandatory?
- Is one child consumer being temporarily non-responsive acceptable?
- Can records continue to be received on other partitions?
- Can a listener be paused while still considering the instance ready?
- When should the instance be removed from service discovery?

Readiness does not automatically stop the Kafka listener container. If consumption must stop when not-ready, a dedicated pause/stop mechanism is needed with group membership, rebalance, and offset impacts considered.

### 11.3. Avoiding liveness restart loops

If the cause is a database timeout, restarting the pod may not help. The new pod immediately hits the same database outage, the consumer group rebalances again, and extra load may be generated.

Only use liveness failures to trigger restarts when there is evidence of unrecoverable process/thread state or a tested policy. For transient dependency failures, use timeouts, circuit breakers, backoff, and readiness/degraded states.

## 12. Consumer liveness and group heartbeats

The Kafka consumer group protocol maintains membership. Classic configurations commonly known include:

- `heartbeat.interval.ms`: heartbeat cadence.
- `session.timeout.ms`: how long the broker waits for heartbeats before removing a member.
- `max.poll.interval.ms`: maximum time between polls.

A consumer thread can be inside a listener while the client still keeps heartbeats active. However, if `poll()` is not called for longer than `max.poll.interval.ms`, the client/group protocol can view the member as no longer progressing.

### 12.1. Two timeouts serve different goals

~~~text
Heartbeat:
  "Is the consumer still maintaining connection/membership?"

max.poll.interval:
  "Is the consumer continuing to fetch and process records at the poll cadence?"

Spring NonResponsiveConsumerEvent:
  "Did the container observe poll progress falling behind the internal threshold?"
~~~

This is an operational interpretation, not a specification of every protocol detail across every Kafka version. Newer group protocols can alter how heartbeats and membership are managed.

### 12.2. Static membership has nuances

With static membership (`group.instance.id`), behavior when a consumer exceeds `max.poll.interval.ms` can differ in when partitions are reassigned compared to dynamic members. Do not assume partitions always move immediately when a listener blocks; check Kafka client version, group protocol, and coordinator logs.

## 13. Other events not to confuse with non-responsive

| Event | Indicates | What to investigate |
|---|---|---|
| `ConsumerStartedEvent` | Consumer has started | Subsequent assignment and poll progress |
| `ConsumerFailedToStartEvent` | Consumer failed to start within startup timeout | Executor/lifecycle/startup capacity |
| `ConsumerStoppedEvent` | Consumer stopped | Shutdown, fatal error, lifecycle |
| `ListenerContainerIdleEvent` | No records received during idle interval | Input traffic, assignment, pause |
| `ListenerContainerNoLongerIdleEvent` | Consumer received records again after idle | Data flow resumed |
| `NonResponsiveConsumerEvent` | No poll progress within monitor threshold | Blocked thread, poll delay, dependency |
| `ConsumerPausedEvent` | Consumer paused | Backpressure/maintenance reason |
| `ConsumerResumedEvent` | Consumer resumed | Delivery and backlog progress |

Idle events can be completely normal when a topic is empty. A non-responsive event is about poll progress; it needs investigation even when lag is still small because the consumer may have just blocked before backlog accumulated.

## 14. Designing dependency timeouts

Consumer threads commonly call databases, HTTP services, caches, or other services. Each dependency needs timeouts fitting inside the record processing budget.

Simple example budget:

~~~text
Target poll/processing budget: 30 seconds

Database acquisition + query: max 5 seconds
Downstream HTTP: max 8 seconds
Business computation: max 5 seconds
In-listener retry/backoff: explicit cap
Cleanup/commit margin: remaining time
~~~

These are illustrative numbers. Calculate worst-case/batch time and `max.poll.interval.ms` with an appropriate margin; do not sum individual timeouts while forgetting retries and queueing.

### 14.1. Timeouts at every layer

Consider:

- Connection timeout.
- Read/response timeout.
- Overall call deadline.
- Database connection acquisition timeout.
- Query timeout.
- Transaction timeout.
- Future wait timeout.
- Retry count and backoff cap.

An outer-layer timeout does not necessarily cancel an underlying socket/query. Understand the cancellation semantics of your client and driver.

### 14.2. Do not retry synchronously for too long on the consumer thread

If a listener retries an HTTP call 10 times at 10 seconds each, total time can exceed the poll interval. Consider error handler backoff, retry topics, outbox, or an asynchronous state machine according to business requirements.

Retry topics can offload records to another consumer flow so the main consumer continues, but transaction/offset semantics and idempotency must be understood. Moving to async must also never commit offsets before appropriate durability.

## 15. Listener processing duration and max.poll.interval.ms

Measure processing time at record and batch levels:

| Metric | Meaning |
|---|---|
| Listener duration p50/p95/p99 | Distribution of processing times |
| Max poll-to-poll interval | Actual interval between polls |
| Batch size | Number of records processed in one poll |
| Error handler/backoff duration | Retry/backoff duration |
| Dependency latency | DB/HTTP/cache time |
| Commit latency | Time to confirm offsets/transactions |

If `max.poll.interval.ms` is 300 seconds yet listener p99 is only 1 second, a liveness issue may be caused by a deadlock or a few requests hanging indefinitely. If batch processing p99 is 280 seconds, the margin is too thin and batch size/concurrency should be revisited.

### 15.1. Do not look only at p99

A listener with good p99 where one specific record hangs indefinitely can still prevent the consumer from polling. Observe oldest in-flight age, max duration, and `NonResponsiveConsumerEvent`.

### 15.2. Poll timeout is not a processing timeout

`pollTimeout` only controls how long `poll()` waits for records. It does not bound how long the listener method runs. Increasing poll timeout does not solve an HTTP call hanging inside a listener.

## 16. Handling non-responsive events by severity

Not every event requires a restart. A tiered workflow:

~~~text
NonResponsiveConsumerEvent
          |
          v
Record incident + metrics + listener/instance
          |
          v
Capture thread dump / inspect dependencies
          |
          v
Did consumer return to poll on its own?
       /           \
     Yes            No
     |               |
     v               v
Monitor lag      Check deadlock /
and processing   blocked I/O / thread
                     |
                     v
             Is there a recovery path?
                /          \
              Yes           No
              |              |
              v              v
      Controlled         Restart/replace
      recovery, cooldown per tested policy
~~~

This is a guiding decision flow. Actual action depends on listener criticality, transaction semantics, group state, and duplicate-record handling capability.

### 16.1. Prioritize fixing the root cause

- Hanging HTTP: fix timeouts/circuit breakers or restore downstream.
- Exhausted DB pool: release connections, tune transactions or capacity.
- Lock deadlock: fix lock ordering/code and handle transactions.
- CPU saturation: address throttling/GC/algorithms.
- Executor starvation: add threads or isolate pools.
- Kafka network issue: check brokers/network/credentials.

Restarting is only useful when process/thread state cannot self-recover or the container has entered an uncontinuable state.

### 16.2. Do not repeatedly stop/start inside the event callback

If the callback immediately calls stop/start on every received event, it can:

- Cause a restart loop.
- Trigger continuous group rebalances.
- Cause duplicate processing from uncommitted records.
- Lose thread dump evidence before investigation.
- Increase load on brokers/downstream.

If self-recovery is needed, use a dedicated supervisor with state, cooldowns, attempt caps, and auditing. The supervisor must avoid concurrent operations on the same container from multiple controllers.

## 17. Managing containers with KafkaListenerEndpointRegistry

For listeners declared with `@KafkaListener`, containers can be looked up via `KafkaListenerEndpointRegistry`:

~~~java
@Service
public class OrdersContainerSupervisor {

    private final KafkaListenerEndpointRegistry registry;

    public OrdersContainerSupervisor(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isContainerRunning(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);

        return container != null && container.isRunning();
    }
}
~~~

This example only checks lifecycle. It **does not prove the consumer thread is responsive**. Combine it with event/last-poll state and metrics.

### 17.1. Restarts require a procedure

Once a container restart is determined to be appropriate:

1. Verify the container exists and no restart is currently in progress.
2. Record incident context and thread diagnostics before stopping if possible.
3. Use the version-appropriate container/registry lifecycle API.
4. Wait for stop completion per supported API.
5. Start again according to desired state.
6. Confirm consumer startup event, partition assignment, and poll progress.
7. Check lag, redelivery, and idempotency.

Do not assume that a stop/start call returning means all consumer threads have been reinitialized. Use lifecycle callbacks/events to confirm.

### 17.2. One stuck child consumer in a concurrent container

`ConcurrentMessageListenerContainer` can manage multiple child consumers. One non-responsive child does not necessarily mean all children are failing. Identify the specific child/partition before restarting the entire container, as container-level operations can cause a broader rebalance.

## 18. Observability: essential metrics

A consumer liveness dashboard should combine:

| Metric/Signal | Question |
|---|---|
| Time since last poll | How long has the consumer gone without polling? |
| `NonResponsiveConsumerEvent` count | How many times was the threshold exceeded? |
| Listener processing duration | Is the listener taking too long? |
| Max poll interval observed | Is there a risk of exceeding `max.poll.interval.ms`? |
| Consumer lag by partition | Is backlog growing? |
| Records consumed rate | Is the consumer still receiving data? |
| Business success rate | Is work completing? |
| Active consumer thread count | Are enough threads running? |
| Executor active/queue/rejection | Is there thread starvation? |
| JVM CPU/GC/heap | Is the JVM overloaded? |
| Dependency latency/error | Is DB/HTTP blocking? |
| Rebalance count/duration | Is group membership unstable? |

Not all of these metrics are available automatically in every Spring Kafka version. Some require Micrometer, Kafka client metrics, JMX exporters, and application instrumentation.

### 18.1. Alert on duration and impact

A single event can be an early warning; critical alerts should be based on:

- Non-responsiveness persisting across multiple monitor cycles.
- Critical listeners having no poll progress.
- Rising lag or oldest record age exceeding SLO.
- Group beginning to rebalance or losing assignments.
- Dropping business success rate.

Do not page merely because a low-traffic consumer or empty topic is quiet. However, if poll progress stops and a critical listener has backlog, escalate the alert.

### 18.2. Do not use event count in place of duration

If the monitor emits an event every cycle while the consumer remains stuck, the counter increases rapidly. Incident duration or a `last-poll-age` gauge measures actual elapsed time; a counter only counts observations.

## 19. Example readiness policy

A service can store consumer liveness state:

~~~java
@Component
public class ConsumerLivenessState {

    private final AtomicLong lastNonResponsiveAt =
            new AtomicLong(0L);

    private final AtomicLong lastResponsiveAt =
            new AtomicLong(System.currentTimeMillis());

    @EventListener
    public void onNonResponsive(
            NonResponsiveConsumerEvent event) {
        lastNonResponsiveAt.set(System.currentTimeMillis());
    }

    public void markPollProgressRecovered() {
        lastResponsiveAt.set(System.currentTimeMillis());
    }

    public boolean hasRecentFailure(long windowMs) {
        long failedAt = lastNonResponsiveAt.get();
        return failedAt > 0
                && System.currentTimeMillis() - failedAt < windowMs
                && lastResponsiveAt.get() < failedAt;
    }
}
~~~

This is an illustrative state model, **not a complete implementation**: you need a reliable signal confirming poll progress recovery, separation of listener IDs/instances, and handling for multiple child consumers. Never call `markPollProgressRecovered()` simply because the process received an HTTP request or the container reports running.

### 19.1. HealthIndicator

A custom Spring Boot `HealthIndicator` can read the state above to report `UP`/`DOWN` or a custom status. Determine whether it maps to the readiness or liveness group according to Spring Boot version/configuration.

Do not return `DOWN` for the entire application just because an optional consumer is non-responsive if the service can still perform other critical duties. You can use a degraded status or separate health components per listener.

### 19.2. Readiness does not control the consumer directly

When readiness is `DOWN`, Kubernetes typically stops sending Service traffic to the pod; it does not automatically stop the Kafka listener. If policy requires stopping Kafka record consumption, the application needs separate pause/stop control while considering group membership, rebalances, and offset behavior.

## 20. Consumer thread liveness with retries and error handlers

A failing record can prevent the consumer from returning to poll during backoff if retries run synchronously on the consumer thread.

Example:

~~~text
poll() -> record
       |
       v
listener throws
       |
       v
blocking retry / backoff
       |
       v
retry attempt
       |
       v
listener success or recover
       |
       v
next poll()
~~~

If backoff is long or there are many retries, the poll-to-poll interval can exceed thresholds. Calculate total time:

~~~text
Total attempt budget
  = Σ processing time
  + Σ backoff time
  + error handling / recovery time
~~~

Compare total time against `max.poll.interval.ms` and monitor thresholds.

### 20.1. Retry topics can decouple wait time

Non-blocking retry topics can move records to another topic and let the main consumer continue, rather than holding the consumer thread for long backoffs. However, the topology introduces additional consumers, offsets, and recovery stages; monitor each group/topic.

Do not conclude the main consumer group is healthy simply because lag dropped after moving records to a retry topic. Events may still be waiting for processing in the retry pipeline.

### 20.2. DLT publishing can also block

If the recoverer sends to a DLT synchronously or waits on a producer future, DLT broker/network failures can hold the consumer thread. Set timeouts for publish/recovery and ensure source offsets are not committed until the DLT write is safely persisted per policy.

## 21. Consumer thread liveness and Kafka transactions

In a transactional listener container, the consumer thread can hold a Kafka transaction open while the listener executes. If the listener blocks:

- Transaction duration grows.
- The producer transaction can time out.
- The consumer does not return to poll.
- Group progress can be affected.
- Downstream `read_committed` consumers may wait for LSO if the transaction stays open.

When receiving a non-responsive event in a transactional flow, inspect:

1. Listener processing duration.
2. Kafka transaction start/commit/abort.
3. Transaction timeout.
4. Database transactions, if any.
5. Producer fencing.
6. Group poll/heartbeat progress.

Do not raise the transaction timeout indefinitely to mask a blocked listener. Nor should you kill the process immediately while a transaction is open without assessing side effects and redelivery.

## 22. Multi-threading and async processing

If the listener dispatches work to an executor:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
}
~~~

The consumer thread can return to poll quickly, yet the worker may be blocked. In that case:

- Consumer liveness can look healthy.
- Kafka lag can drop if offsets are committed.
- Internal queues can grow.
- Business completion slows down or is lost if the process crashes.

This is **backlog shifted out of Kafka**, not eliminated.

### 22.1. Measure worker liveness too

If using async processing, track metrics:

- Queue depth.
- Oldest queued task age.
- Active worker count.
- Worker rejection count.
- Task success/failure rate.
- Time from Kafka receive to durable completion.

Do not monitor only the consumer thread and conclude the end-to-end pipeline is healthy.

### 22.2. Bounded queues and backpressure

Unbounded queues can exhaust JVM heap when the consumer polls faster than workers drain. Use bounded queues, pause/backpressure, or durable work-queue designs. When the queue is full, ack/commit decisions must be handled so records are never lost.

## 23. Thread liveness and JVM deadlocks

A deadlock involving the consumer thread can halt poll progress. Thread dumps typically show:

~~~text
Found one Java-level deadlock:

"orders-consumer-1":
  waiting to lock <0x...> held by "inventory-worker-2"

"inventory-worker-2":
  waiting to lock <0x...> held by "orders-consumer-1"
~~~

This is illustrative output. When detected:

1. Save thread dumps and JVM diagnostics.
2. Identify lock owners and code paths.
3. Check whether transaction/database locks form a related wait cycle.
4. Use timeouts/lock ordering or narrow `synchronized` scope.
5. If unrecoverable, replace the instance per runbook.

Never attempt `Thread.stop()` or arbitrary interrupts to free a thread; objects/resources can be left in an inconsistent state.

## 24. Rebalances and duplicate delivery after a stuck thread

If a consumer exceeds `max.poll.interval.ms` or loses its session, the Kafka group can rebalance partitions. Uncommitted records can be redelivered to another consumer.

Consequences:

- The listener may have executed side effects while the offset was not committed.
- The new consumer receives the record again.
- Database updates or HTTP side effects can repeat.
- Old transactions may abort.

Thus, consumer thread liveness connects directly to idempotency:

- Use stable event IDs.
- Inbox/processed-events tables.
- Unique constraints.
- Side effects inside appropriate DB transactions.
- Never ack before work is durable.

Restarting the consumer does not guarantee zero duplicates; it can cause uncommitted records to be redelivered under at-least-once semantics.

## 25. Runbook: NonResponsiveConsumerEvent appears

1. Record listener ID, instance/pod, partitions, and time-since-last-poll.
2. Check whether the container is running, paused, or stopping.
3. Check consumer group state and rebalance logs.
4. Capture at least two thread dumps spaced a few seconds apart.
5. Identify whether the consumer thread is blocked on HTTP, database, locks, futures, or a CPU loop.
6. Check `max.poll.interval.ms` and dependency timeouts.
7. Compare listener duration, batch size, and error handler/backoff.
8. Check consumer lag and oldest record age.
9. Fix or restore the dependency/root cause.
10. Verify the consumer returns to poll, group assignment stabilizes, and lag starts decreasing.

Do not restart immediately before saving diagnostics if the incident needs investigation and diagnostics can be collected safely.

## 26. Runbook: container running but not processing records

1. Confirm container ID and `isRunning()`.
2. Check `NonResponsiveConsumerEvent` or time since last poll.
3. Check partition assignment and group membership.
4. Check whether the topic has new records or existing lag.
5. Check pause state and pause reasons.
6. Inspect consumer thread dumps.
7. Check whether the listener/error handler is retrying/blocking.
8. Check deserialization/conversion failures prior to the listener.
9. Confirm the consumer is actually calling `poll()` again.

If lag is 0 and the topic has no data, a quiet listener may be normal. Distinguish having no work to do from being unable to work.

## 27. Runbook: consumer becomes non-responsive after a downstream timeout

1. Locate the dependency being called in the stack trace.
2. Check whether connect/read/call timeouts are configured.
3. Check whether retries multiply total time beyond the poll budget.
4. Check circuit breakers and connection pools.
5. Determine whether transactions/DB locks are held while waiting on the network.
6. Restore the dependency or enable an appropriate degraded mode.
7. Wait for the listener to finish/time out per policy.
8. If the thread cannot recover, perform controlled container/process recovery.
9. Monitor redelivery and idempotency after rebalancing.

Do not mechanically increase `max.poll.interval.ms` to cover for an HTTP request without timeouts.

## 28. Runbook: liveness alert but consumer group has not rebalanced

1. Check Spring monitor thresholds and poll timeout.
2. Check heartbeat/session timeouts.
3. Check `max.poll.interval.ms`.
4. Check whether the consumer thread is stuck inside the listener while still maintaining heartbeats.
5. Check the group protocol and static membership.
6. Determine whether partitions still belong to the old consumer or were reassigned.
7. Check lag and side effects of in-flight records.
8. Choose recovery based on thread state, not solely on the fact that the group has not rebalanced.

Unchanged group membership does not immediately mean the consumer thread is healthy.

## 29. Runbook: non-responsiveness repeats after restart

1. Compare thread dumps before and after restart.
2. Determine whether the root cause repeats along the same dependency/code path.
3. Check pool sizing, CPU limits, and connection pools.
4. Check batch size, concurrency, and retry budget.
5. Check whether restarts are causing rebalance storms or duplicate side effects.
6. Add circuit breakers/timeouts or fix locks/thread pools.
7. Cap automatic restarts and alert when attempts are exceeded.
8. Close the incident only once poll progress and business completion stabilize.

If the same stack trace appears after every restart, restarting is not a fix.

## 30. Testing consumer thread liveness

Integration tests should confirm the monitor detects stalled poll progress while avoiding false positives when listeners operate normally.

### 30.1. Fast listener

1. Start a test Kafka broker and listener container.
2. Configure poll timeout/monitor thresholds with adequate headroom.
3. Send records.
4. Verify the listener processes records and continues polling.
5. Verify no non-responsive events are emitted under normal conditions.

### 30.2. Controlled blocked listener

1. Use a latch to hold the listener method unfinished.
2. Configure thresholds short enough for the test.
3. Wait for the monitor to emit `NonResponsiveConsumerEvent`.
4. Verify listener/container metadata can be identified.
5. Release the latch.
6. Verify the consumer returns to polling and processes subsequent records.

The test must release the latch in `finally` to avoid hanging the test suite.

### 30.3. Downstream timeout

1. Mock a slow or timing-out HTTP/DB dependency.
2. Verify the listener does not wait forever.
3. Check events/metrics against thresholds.
4. Check error handler/retry policy.
5. Verify consumer progress recovers once the dependency becomes healthy.

### 30.4. Batch exceeding poll budget

1. Create a batch with a controlled processing duration.
2. Measure total batch processing time.
3. Compare against `max.poll.interval.ms`.
4. Verify rebalancing or poll monitoring behaves as expected for the version.
5. Tune batch/concurrency and repeat the test.

Do not set test timeouts so tight to real-world boundaries that they depend on CI scheduling; leave adequate tolerance.

### 30.5. Thread starvation/deadlock

1. Provide an undersized executor or intentionally hold a lock in the test.
2. Verify consumer poll progress stops.
3. Capture thread dumps or worker state.
4. Release resources.
5. Verify the consumer resumes or the container recovers per policy.

This is fault injection intended strictly for isolated test environments.

### 30.6. Testing readiness and liveness separately

1. Make the consumer non-responsive while keeping the HTTP server/process alive.
2. Verify readiness reflects the policy for critical listeners.
3. Verify liveness does not enter a restart loop solely because Kafka/dependencies are temporarily unavailable.
4. Simulate a deadlock/unrecoverable state and verify the liveness policy handles it as designed.
5. Recover and verify health states return to normal.

## 31. Common mistakes

**Checking only whether the process is alive.** The JVM can run while the consumer thread fails to return to `poll()`.

**Treating NonResponsiveConsumerEvent as proof the broker is down.** The listener may be blocked on a database or HTTP call.

**Confusing idle with non-responsive.** An empty topic with steady polling is valid idleness.

**Confusing container running with consumer progress.** Lifecycle state does not prove polling is occurring.

**Increasing only session.timeout.ms.** It does not fix a blocked listener and does not replace `max.poll.interval.ms`.

**Increasing max.poll.interval.ms indefinitely.** Delays detection of stalled consumers and hides overly long batch processing.

**Setting monitor thresholds too low.** Healthy listeners can be flagged as non-responsive.

**Setting thresholds too high.** Incidents are detected late while lag and record age grow.

**Calling KafkaConsumer from the event thread.** `KafkaConsumer` is not thread-safe for arbitrary operations from other threads.

**Restarting immediately inside the event callback.** Can cause restart/rebalance loops and destroy diagnostics.

**Omitting timeouts on dependencies or Future.get().** The consumer thread can wait forever.

**Monitoring only the consumer thread when processing asynchronously.** Worker queues can still pile up even when the poll thread looks healthy.

**Increasing concurrency when the database is out of connections.** Worsens downstream overload.

**Ignoring duplicate delivery after rebalances.** Side effects can repeat if not idempotent.

**Making non-responsive event count the sole metric.** Duration, last poll age, lag, and recovery signals are also needed.

## 32. Implementation checklist

### Poll/liveness configuration

- [ ] Understood `pollTimeout`, `monitorInterval`, and `noPollThreshold` for the exact Spring Kafka version.
- [ ] Monitor thresholds fit processing p95/p99 and batch size.
- [ ] `max.poll.interval.ms` provides sufficient processing budget while still detecting stalled consumers.
- [ ] `session.timeout.ms` and heartbeat settings match the group protocol.
- [ ] Dependency I/O and future waits have timeouts.

### Application events and diagnostics

- [ ] Handler exists for `NonResponsiveConsumerEvent`.
- [ ] Handler is lightweight, performing no heavy I/O or recursive restarts.
- [ ] Logs listener ID, instance, time-since-last-poll, and partitions when supported by API.
- [ ] Procedure exists to capture thread dumps safely.
- [ ] Never manipulates `KafkaConsumer` directly from the event thread.
- [ ] Repeated events are deduplicated into incidents with start/end timestamps.

### Health and recovery

- [ ] Process liveness, container state, consumer progress, group membership, and business progress are distinguished.
- [ ] Readiness policy reflects critical listeners.
- [ ] Liveness does not depend directly on temporarily unavailable Kafka brokers.
- [ ] Controlled recovery, cooldowns, and restart caps are in place.
- [ ] Idempotency protects side effects on rebalances/redelivery.
- [ ] Async worker queues also have health/backpressure metrics.

### Monitoring and testing

- [ ] Last poll age, listener duration, lag, and business success rate metrics exist.
- [ ] Executor, CPU, GC, and DB/HTTP latency metrics exist.
- [ ] Alerts trigger on duration and SLO impact.
- [ ] Tested blocked listeners, dependency timeouts, and thread starvation.
- [ ] Tested consumer recovery and continued polling after releasing blocks.
- [ ] Tested that readiness/liveness do not create restart loops.
- [ ] Runbooks exist for non-responsive events, rebalances, and duplicate delivery.

## Conclusion

**Consumer thread liveness** is the consumer's ability to keep progressing through the `poll()` loop and processing records within bounded time. Spring Kafka can emit `NonResponsiveConsumerEvent` when the monitor detects a consumer has not polled within a threshold derived from `pollTimeout` and `noPollThreshold`. This event helps expose blocked listeners, dependency timeouts, lock contention, or thread starvation; it does not by itself prove brokers are down, the thread is dead, or the process must restart immediately.

To operate reliably, separate process liveness, container lifecycle, poll progress, Kafka group heartbeats, and business completion. Use thread dumps along with listener/dependency metrics to find root causes, budget timeouts and retries within `max.poll.interval.ms`, and build readiness/liveness policies that avoid restart loops on transient dependency faults. When a consumer recovers or rebalances, still guard side effects with idempotency because uncommitted records may be redelivered. **A healthy consumer is not just a live thread; it is a processing loop that continues polling, completing work, and advancing offsets safely.**
