# ConsumerStoppingEvent

In Spring Kafka, a consumer does not merely exist in a **running** or **stopped** state. The listener container also transitions through multiple lifecycle steps: initializing the consumer thread, joining the consumer group, polling records, processing records, receiving a stop request, and finally closing `KafkaConsumer`. Spring Kafka publishes **application events** so the application can observe these critical transitions.

**`ConsumerStoppingEvent`** is an event published by the consumer thread **just before the consumer stops operating and is closed**. This is an appropriate moment to record that the consumer is preparing to terminate and clean up certain resources bound to that consuming thread. This event is especially useful when the application uses `ThreadLocal`, thread-bound context, or resources owned by the consumer thread.

However, `ConsumerStoppingEvent` **is not** a promise that all side effects have completed, offsets have committed successfully, or the consumer group is no longer rebalancing. Nor is it a hook to call `consumer.close()` a second time yourself. For reliable operations, distinguish this event clearly from `ConsumerStoppedEvent`, `ContainerStoppedEvent`, and partition revocation callbacks.

## 1. Position in the Kafka listener container lifecycle

A simplified processing flow can be described as follows:

```text
Spring application starts
          |
          v
Kafka listener container starts
          |
          v
Consumer thread initializes
          |
          v
ConsumerStartingEvent / ConsumerStartedEvent
          |
          v
poll() -> @KafkaListener -> commit/retry/recovery
          |
          v
Receive stop request or enter consumer termination branch
          |
          v
ConsumerStoppingEvent
          |
          v
Close KafkaConsumer, terminate consumer thread
          |
          v
ConsumerStoppedEvent
          |
          v
ContainerStoppedEvent (when container terminates)
```

The diagram shows **functional relationships**, not a guarantee of every callback ordering detail across all versions and container types. For example, `ConcurrentMessageListenerContainer` contains child containers; each child has its own consumer thread and lifecycle. Stopping the parent container once can lead to multiple `ConsumerStoppingEvent` and `ConsumerStoppedEvent` occurrences.

The key point is that `ConsumerStoppingEvent` occurs **before the consumer closes completely**. If you only listen to `ConsumerStoppedEvent`, the consumer's resources are already in a different state. If you only listen to `ContainerStoppedEvent`, the application only sees container-level state after the associated consumers finish.

## 2. Which event to use for which task?

| Event or callback | Timing/context | Appropriate purpose |
|---|---|---|
| `ConsumerStartingEvent` | Consumer thread begins initialization | Observe consumer creation and startup timing |
| `ConsumerStartedEvent` | Consumer begins operating/polling | Mark startup complete, initialize per-thread observation if appropriate |
| `ConsumerStoppingEvent` | Consumer thread prepares to terminate, before closing consumer | Clean up thread-bound resources, record lifecycle log/metric |
| `ConsumerStoppedEvent` | Consumer has stopped | Record stop outcome and stop reason if supported by event/version |
| `ContainerStoppedEvent` | Listener container has stopped | Observe overall container state |
| `ListenerContainerIdleEvent` | Container received no records within configured idle interval | Detect temporarily idle stream; does not mean consumer is stopping |
| `ConsumerAwareRebalanceListener` | Partition revoke/assign during rebalance | Manage per-partition state and ownership |

An *idle* consumer can still poll and maintain membership. A *paused* consumer can still keep polling to maintain group membership. A consumer going through a *rebalance* may lose some partitions while staying alive and polling on other partitions. Those events **are not equivalent** to the consumer thread actually terminating.

Therefore, do not use `ConsumerStoppingEvent` as the sole solution to track partition revocations or detect an application lacking records. Each lifecycle milestone needs the right observation tool.

## 3. Registering a listener with `@EventListener`

Spring publishes `ConsumerStoppingEvent` through the application event infrastructure. A Spring bean can receive the event with the `@EventListener` annotation:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStoppingEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerLifecycleLogger {

    private static final Logger log = LoggerFactory.getLogger(
            KafkaConsumerLifecycleLogger.class);

    @EventListener
    public void onConsumerStopping(ConsumerStoppingEvent event) {
        log.info(
                "Kafka consumer stopping: source={}, thread={}",
                event.getSource(),
                Thread.currentThread().getName());
    }
}
```

The illustrative code receives the event and logs briefly. `getSource()` describes the event publisher per Spring application events; in a multi-container topology, it is not necessarily the `@KafkaListener` name operators see in source code. When mapping back to listener ID/group ID is needed, build a clear container-identification mechanism and verify the values provided by the version in use.

`@EventListener` works with a Spring context that has an appropriate event multicaster and does not require manual invocation from the listener. If the bean is not component-scanned or the event is published in a different application context, the method will not be called.

### Using `ApplicationListener` when an explicit type is needed

An equivalent approach is implementing the interface:

```java
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.event.ConsumerStoppingEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerStopObserver
        implements ApplicationListener<ConsumerStoppingEvent> {

    @Override
    public void onApplicationEvent(ConsumerStoppingEvent event) {
        // Record the event or clean up resources bound to the consumer thread.
    }
}
```

Usually only **one of the two approaches** is needed for the same job. Do not register both and run cleanup twice if the logic is not idempotent.

## 4. Most important note: the event is published from the consumer thread

Under Spring's default application event multicaster mechanism, listeners receiving the event are called **synchronously on the event-publishing thread**. For `ConsumerStoppingEvent`, the publishing thread is the consumer thread that the container is about to terminate.

This has two important consequences:

1. You can clean up `ThreadLocal` values set on **the same consumer thread** because the callback runs on the thread owning that data.
2. A callback that is too slow or blocked will prolong consumer termination. It can lengthen shutdown, cause timeouts, or hinder container termination.

If the application configures `ApplicationEventMulticaster` to run with an asynchronous `TaskExecutor`, or annotates the event-handling method with `@Async`, the event listener may run on **another thread**. In that case, `ThreadLocal.remove()` only clears the value on the event listener thread, **not the consumer thread's `ThreadLocal`**.

```text
Synchronous default:

Consumer thread ---- publish ConsumerStoppingEvent
       |                       |
       |                       v
       +---- @EventListener runs on same thread
                               |
                               v
                      ThreadLocal.remove() on right thread

Asynchronous multicaster:

Consumer thread ---- publish event ---> Executor thread
                                           |
                                           v
                                  ThreadLocal.remove()
                                  only on executor thread
```

**Rule:** if cleanup requires thread affinity, use a synchronous event listener. Do not directly access `KafkaConsumer` attached in the event from an async event handler because `KafkaConsumer` is not thread-safe.

## 5. Example cleaning up `ThreadLocal` when consumer stops

An application may create caches, formatter state, or a per-consumer-thread processing context to avoid allocating objects on every record. If not released in time, resources may retain references to large objects or hold connections after the consumer has stopped.

Example of a `ThreadLocal` holding an application object with resources to close:

```java
import org.springframework.stereotype.Component;

@Component
public class ConsumerThreadResources {

    private final ThreadLocal<ConsumerSession> current = new ThreadLocal<>();

    public ConsumerSession getOrCreate() {
        ConsumerSession session = current.get();
        if (session == null) {
            session = new ConsumerSession(); // application-defined class
            current.set(session);
        }
        return session;
    }

    public void cleanupCurrentThread() {
        ConsumerSession session = current.get();
        current.remove();

        if (session != null) {
            session.close();
        }
    }
}
```

Assume `ConsumerSession` is an application class with a `close()` method designed specifically for the processing thread. It is **not** `org.apache.kafka.clients.consumer.Consumer` itself or a shared Kafka producer. The business listener can use the same `ConsumerThreadResources` bean:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-service")
public void onOrder(OrderEvent event) {
    ConsumerSession session = threadResources.getOrCreate();
    orderService.handleIdempotently(event, session);
}
```

When the consumer terminates, clean up state via the event listener:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStoppingEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerThreadCleanup {

    private static final Logger log = LoggerFactory.getLogger(
            ConsumerThreadCleanup.class);

    private final ConsumerThreadResources resources;

    public ConsumerThreadCleanup(ConsumerThreadResources resources) {
        this.resources = resources;
    }

    @EventListener
    public void onStopping(ConsumerStoppingEvent event) {
        try {
            resources.cleanupCurrentThread();
        }
        catch (RuntimeException ex) {
            log.warn("Could not clean consumer thread resource", ex);
        }
    }
}
```

For the example to work properly, `ConsumerThreadResources` must be a shared bean between the business listener and the cleanup listener; **application event dispatch must be synchronous**; `ConsumerSession.close()` must handle repeated calls or already-closed resources. If `close()` throws a checked exception, handle or declare it appropriately in that class.

`ThreadLocal.remove()` runs before closing the resource to reduce the risk of stale state being retained if closing fails. If resources must be released in a different order, define an appropriate sequence and monitor cleanup errors.

## 6. Which resources are suitable to clean up here?

`ConsumerStoppingEvent` is best suited for resources living **for the consumer thread's lifecycle**, not a business operation needing a commit or rollback decision.

| Resource | Should it be handled on this event? | Reason |
|---|---|---|
| `ThreadLocal` context/cache | Yes, if created on the consumer thread | Must be cleared on the exact thread to prevent reference leaks |
| Application-managed thread-bound formatter/session | Yes, if it has an appropriate `close()` | Shares the same lifetime as the consumer thread |
| Per-thread/container metric/gauge | Can record stopping state | Useful to avoid reporting a consumer alive after termination |
| Container-managed `KafkaConsumer` | **Do not close yourself** | The container owns its lifecycle |
| Uncommitted consumer offsets | **Do not choose this event as primary commit point** | Insufficient guarantees for transaction/assignment/ack state |
| Single-record database transaction | Do not defer until consumer stops | Must complete within record-processing or unit-of-work boundaries |
| In-flight HTTP requests | Do not wait indefinitely in callback | Blocking cleanup prolongs shutdown |
| Application-wide shared connection pool | Usually no | Multiple consumers may share it; closing once when one consumer stops breaks others |

If a resource only has a **single-record** lifetime, it is better to use `try/finally`, `try-with-resources`, or transaction boundaries directly inside the business method. Waiting until `ConsumerStoppingEvent` to close per-record resources can let thousands of resources accumulate while the consumer runs long-term.

## 7. What can `event.getConsumer()` be used for?

`ConsumerStoppingEvent` provides a reference to the terminating Kafka consumer in Spring Kafka versions that support this property. This is a useful detail for observing or applying specific cleanup, but it requires extreme caution.

```java
@EventListener
public void onConsumerStopping(ConsumerStoppingEvent event) {
    Consumer<?, ?> consumer = event.getConsumer();
    // Use only if genuinely needed to observe the consumer on the same thread.
    // Do not call consumer.close(), subscribe(), poll(), or commitSync().
}
```

**Do not use this reference to re-control the consumer lifecycle.** The container is performing shutdown and is responsible for closing the consumer, handling commits/offsets, and releasing resources. Actively calling `close()`, `poll()`, `seek()`, or commit operations from the callback can conflict with the lifecycle or produce hard-to-control states.

Do not store `Consumer` in static fields, caches, or queues, or send it to another executor. Once the event finishes, the consumer may already be closed; keeping the reference does not make it safe to reuse.

`assignment()` or group metadata read at stopping time is also just a **snapshot**. Partitions may already be revoked or in the middle of revocation. If you need accurate per-partition ownership management, use rebalance callbacks instead of treating the stop-time snapshot as truth.

## 8. Distinguishing stopping consumer from stopping container

A listener container may manage one consumer or multiple consumers. With `ConcurrentKafkaListenerContainerFactory`, configuring `concurrency` typically creates multiple consumer child containers to process partitions in parallel.

```text
ConcurrentMessageListenerContainer: ordersListener
             |
       +-----+-----+
       |     |     |
     Child A Child B Child C
       |     |     |
     Kafka   Kafka  Kafka
     consumer consumer consumer

Request to stop parent container
       |
       +--> A's ConsumerStoppingEvent
       +--> B's ConsumerStoppingEvent
       +--> C's ConsumerStoppingEvent
       |
       +--> ConsumerStoppedEvent instances
       |
       +--> ContainerStoppedEvent on overall completion
```

Each child's event may appear at a different time because one child is processing a slower record or hits an error during shutdown. Therefore, **one `ConsumerStoppingEvent` does not mean the entire listener container has stopped**.

When computing a metric for active consumers, use an appropriate child/container or thread identifier to avoid mistakenly subtracting one stop for the entire group. `concurrency=3` also does not guarantee three partitions are always processing: actual partition count and assignment depend on the topic and consumer group.

If you need to perform a *single step after the entire container stops*, `ContainerStoppedEvent` or a container-level orchestration callback is usually the right choice. Use `ConsumerStoppingEvent` for cleanup specific to each consumer thread.

## 9. What causes the event to be published?

`ConsumerStoppingEvent` is tied to **a consumer actually terminating**, not limited to an operator clicking a stop button. A consumer can terminate when:

- The Spring application context is shutting down normally.
- The listener container is stopped via management API or `KafkaListenerEndpointRegistry`.
- The container stops due to configuration/lifecycle or a severe error requiring termination of the consumer thread.
- The application changes lifecycle state causing the container to stop and restart, creating a new consumer thread.

Do not deduce the exact cause solely from receiving `ConsumerStoppingEvent`. To know whether the consumer stopped normally, due to fencing, due to an error, or due to a special condition, combine `ConsumerStoppedEvent`, framework-version reason attributes, exception logs, and corresponding container events.

Conversely, the following situations **do not necessarily** publish `ConsumerStoppingEvent`:

- A consumer group rebalance where the consumer thread continues running.
- Container temporarily pausing due to downstream overload and then resuming.
- Listener temporarily idle because the topic has no records.
- A record retry by `DefaultErrorHandler` without the consumer terminating.

If the JVM is forcibly killed or the host loses power, application events get no chance to run. Do not build a system that requires receiving this event to detect failures or release resources **in another system**; use leases, timeouts, heartbeats, and idempotency according to proper architecture.

## 10. Rebalance revocation is a different event

An application may need to clean up state when partition `orders-2` moves to another consumer while the old consumer thread keeps running and continues owning `orders-0`.

```text
Consumer A owns orders-0, orders-2
                 |
                 v
             Rebalance
                 |
                 +--> orders-2 is revoked
                 |
                 +--> Consumer A keeps running orders-0

ConsumerStoppingEvent is NOT a replacement hook for the revoke callback
```

To clean up resources or checkpoints **per partition**, use `ConsumerAwareRebalanceListener` or the corresponding assignment/revocation callback mechanism:

```java
factory.getContainerProperties().setConsumerRebalanceListener(
        new ConsumerAwareRebalanceListener() {

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        partitionStateStore.release(partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        partitionStateStore.initialize(partitions);
    }
});
```

`partitionStateStore` is an application-defined object. Ensure callbacks do not perform long blocking I/O; verify callback APIs and ordering against the Spring Kafka version in use. Per-partition cleanup must account for redelivery risk if side effects finished while offsets were not yet committed.

`ConsumerStoppingEvent` can clean up **remaining thread state** when the entire consumer terminates; it does not replace cleaning up a newly revoked partition while the consumer keeps running.

## 11. The event and offset commits: what must not be inferred?

In a Kafka listener, a business method may write to the database successfully yet the consumer loses assignment before committing offsets. Uncommitted records can then be redelivered. `ConsumerStoppingEvent` does not provide a new transaction boundary to make all side effects atomic.

Example:

```text
poll record offset 500
       |
       v
Database UPDATE succeeds
       |
       v
Container starts stopping / consumer loses assignment
       |
       v
ConsumerStoppingEvent published
       |
       v
Offset not yet committed as expected
       |
       v
New consumer may re-read offset 500
```

Do not put `consumer.commitSync()` inside the event listener just to "flush remaining offsets." You need to know which offsets processed successfully, which transactions committed, whether the partitions are still owned, and whether the container is managing offsets/transactions. An arbitrary commit in a shutdown callback can skip incomplete records or conflict with the container's own commits.

The solution is designing proper acknowledgment in the listener, using idempotency/inbox for side effects outside Kafka, and letting Spring Kafka handle commits/recovery per container configuration. When transactional Kafka-to-Kafka consume-transform-produce is needed, use Kafka transactions and commit offsets within the transaction instead of trying to finish via application events.

## 12. Do not let cleanup hang the shutdown process

Shutdown is a sensitive phase: the consumer must release connections and group membership, the application may be receiving a termination signal from orchestration, and the pod/service has a deadline to exit.

In a `ConsumerStoppingEvent` listener, you should:

1. Log briefly; do not flood logs by dumping all assignments/payloads.
2. Clean up `ThreadLocal` and thread-bound resources with fast operations, using timeouts or fallbacks if needed.
3. Catch and log cleanup errors so they do not obscure the primary stop cause.
4. Avoid long blocking calls, sleeping, joining threads, or waiting on external services without timeouts.
5. Do not call `container.stop()`/`start()` again from the callback of the consumer currently stopping.
6. Do not close shared pools, singleton beans, or global executors while other consumers still use them.

A synchronous `@EventListener` running on the consumer thread holds that thread until the callback returns. If a cleanup HTTP call waits 60 seconds while the application only has a 30-second graceful shutdown budget, the process may be killed before the container finishes closing.

If slow cleanup is mandatory and does not require thread affinity, design it as **an overall lifecycle task** (or external workflow) with its own deadline and recovery mechanism. Do not inadvertently turn a per-consumer stopping callback into critical business work that must finish before the application is allowed to stop.

## 13. Impact of a custom `ApplicationEventMulticaster`

Spring can configure `ApplicationEventMulticaster` to use an executor for dispatching events. This can improve decoupling between publisher and observer, but drastically changes what `ConsumerStoppingEvent` means for cleanup.

| Dispatch mode | `Thread.currentThread()` in listener | Cleans consumer's `ThreadLocal`? | Access live `KafkaConsumer`? |
|---|---|---|---|
| Synchronous default | Consumer thread publishing event | Yes, if sharing the `ThreadLocal` holder | Only on same thread and with great care |
| Multicaster using executor | Different executor thread | No, because different thread | Unsafe; consumer may already be closing |
| Method with `@Async` | Async executor thread | No | Should not use Consumer reference |

Therefore, when a system customizes application event handling, verify the **actual thread** in an integration test. If you only need to count stop events or emit a telemetry record without consumer/thread-local state, async may be preferable, though you must account for the fact that events are not guaranteed to complete before the JVM exits.

One design option is splitting two observers: a synchronous observer performs only mandatory cleanup on the consumer thread; the metrics/logging system receives immutable metadata (container ID, timestamp, state) to process separately. Do not pass the raw `Consumer` object to an executor.

## 14. Observing events in multi-consumer systems

In production, an application may have many listener groups for topics, multiple child consumers, and multiple replicas. If each consumer emits a stopping event, design metrics/logs to distinguish contexts.

Useful attributes:

| Attribute | Operational role |
|---|---|
| Application/service name | Identify which service is stopping consumers |
| Instance/pod ID | Distinguish replicas being deployed or restarted |
| Listener/container ID | Distinguish business streams within the same JVM |
| Consumer group | Correlate with Kafka group membership and lag |
| Thread name | Hint which child consumer thread emitted the event |
| Event type and timestamp | Reconstruct the stopping/stopped lifecycle sequence |
| Reason on `ConsumerStoppedEvent` | Distinguish normal termination from certain error paths, if provided by version |

Do not use event IDs or per-record topic-partition-offsets as metric labels for lifecycle events. Lifecycle events belong to **the consumer**, not individual messages. Use metrics with bounded-cardinality labels; put detailed identifiers in logs.

Example of a desirable log sequence during a rolling deployment:

```text
2026-... listener=ordersListener child=0 event=ConsumerStoppingEvent
2026-... listener=ordersListener child=0 event=ConsumerStoppedEvent
2026-... listener=ordersListener event=ContainerStoppedEvent
2026-... instance=new-pod listener=ordersListener event=ConsumerStartedEvent
```

This is an illustrative application-defined structured log format, not Spring Kafka's default format. Log lines from different child containers may interleave because they run on independent threads.

## 15. Common misunderstandings and implementation bugs

| Symptom | Possible cause | How to resolve |
|---|---|---|
| No `ConsumerStoppingEvent` seen on rebalance | Rebalance revokes partitions without stopping consumer thread | Listen to `ConsumerAwareRebalanceListener` for revoke/assign |
| `ThreadLocal` not cleaned up | Event multicaster or `@Async` runs callback on another thread | Use a synchronous listener on consumer thread sharing the `ThreadLocal` holder |
| Container stops very slowly | Cleanup callback makes HTTP/DB calls or waits on long locks | Shorten cleanup, enforce timeouts, and avoid blocking shutdown |
| Single stop produces many events | Container has high `concurrency`, each child consumer emits an event | Count per child consumer, not application-wide |
| Event seen yet offsets still redeliver after restart | Event does not guarantee offset commit | Design proper acks/transactions and idempotent side effects |
| Normal stop logs alerted as errors | Equating stopping with failure | Combine `ConsumerStoppedEvent` reason, exception logs, and deployment events |
| Event listener cleanup closes shared pool | Confusing thread-scoped resources with application-wide singletons | Manage shared pools via Spring bean lifecycle, not consumer stop |
| Event listener throws error making shutdown hard to debug | Cleanup throws unhandled exception | Catch/log cleanup errors, ensure cleanup is idempotent |
| Consumer reference used after stop | Saving `event.getConsumer()` for an async executor | Do not retain/control `KafkaConsumer` outside the consumer thread |
| No event seen when pod receives kill -9 | No graceful shutdown | Design recovery independent of events using timeouts/leases and idempotency |

## 16. Testing `ConsumerStoppingEvent`

To prove listener cleanup works, use a Spring Boot test environment with `@KafkaListener`, `KafkaListenerEndpointRegistry`, a test Kafka broker, and a `CountDownLatch` recording events. Tests should not rely solely on `Thread.sleep()` because shutdown and polling depend on scheduling.

An illustrative event probe:

```java
@Component
public class ConsumerStoppingProbe {

    private final CountDownLatch stopping = new CountDownLatch(1);
    private final AtomicReference<String> stoppingThread =
            new AtomicReference<>();

    @EventListener
    public void record(ConsumerStoppingEvent event) {
        stoppingThread.set(Thread.currentThread().getName());
        stopping.countDown();
    }

    public boolean awaitStop(Duration timeout) throws InterruptedException {
        return stopping.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public String stoppingThread() {
        return stoppingThread.get();
    }
}
```

In an integration test, retrieve the container by listener ID and request stop:

```java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

assertNotNull(container);
container.stop();

assertTrue(stoppingProbe.awaitStop(Duration.ofSeconds(10)));
```

The assertions above show the illustrative structure; the test must ensure the listener has started before calling stop, runs in the right Spring context, and filters the probe to only the consumer/container under test. With high concurrency, a latch counting one event is **insufficient** to prove all child consumers stopped. Count events matching the actual initialized child consumers and combine with `ContainerStoppedEvent`.

Scenarios to test:

1. **Normal stop:** `ConsumerStoppingEvent` is emitted and thread-bound resources are cleaned up.
2. **Stopping multi-child container:** each child emits an event per its lifecycle; cleanup does not mistakenly close another child's resources.
3. **Async event multicaster:** prove `ThreadLocal` cleanup is no longer on the same thread, protecting the architecture from misconfiguration.
4. **Rebalance without stop:** partition revocation is not confused with `ConsumerStoppingEvent`.
5. **Pause/resume:** does not generate stopping events when only pausing record fetching.
6. **Cleanup throws exception:** logic still logs the cause and does not perform unauthorized commits/seeks.
7. **Restart listener:** old thread context is released; the new consumer does not inherit stale state.
8. **Graceful shutdown:** total cleanup time stays within the realistic shutdown budget.

For thread-bound resources, verify post-cleanup state via holder instrumentation or confirming the resource actually closed; merely receiving the event is not enough to prove cleanup ran on the right thread.

## 17. Runbook when consumers are repeatedly stopping/restarting

If many `ConsumerStoppingEvent` occurrences appear in a short window, do not alert solely on event count. Find out **why the consumers are terminating**.

Suggested procedure:

1. **Identify scope:** service, instance, listener/container ID, consumer group, and which children are emitting events.
2. **Reconstruct lifecycle sequence:** look up `ConsumerStartingEvent`, `ConsumerStartedEvent`, `ConsumerStoppingEvent`, `ConsumerStoppedEvent`, `ContainerStoppedEvent`, and startup/shutdown logs.
3. **Distinguish deployment from failure:** check rolling updates, autoscaling, health-check restarts, and stop/start configuration.
4. **Read reason/exceptions:** inspect `ConsumerStoppedEvent` and logs for the actual cause, especially authentication, authorization, fencing, or runtime errors if present.
5. **Cross-check rebalances:** check consumer group assignments, revoke/assign events, and poll intervals to avoid confusing stops with normal rebalances.
6. **Inspect cleanup callbacks:** execution duration, exceptions, thread affinity, and released resources.
7. **Evaluate data impact:** check committed offsets, redelivery, consumer lag, and downstream idempotency after restarts.
8. **Remediate:** fix configuration/resource bugs rather than masking symptoms by disabling lifecycle logging or arbitrarily resetting offsets.

During a rolling deployment, seeing `ConsumerStoppingEvent` occurrences matching the old pod's child consumers is normal. Alerts should trigger on **abnormal frequency**, stop reasons, lag, and restart rates rather than treating every stopping event as an incident.

## 18. Production design principles

When using `ConsumerStoppingEvent` in Spring Kafka, follow these principles:

1. Understand this event as a signal that **the consumer thread is about to stop**, not a signal that the entire consumer group or application has stopped.
2. Use it for cleaning up thread-scoped resources and lifecycle observability; do not push business commits/transactions into the stopping callback.
3. Keep the event listener **synchronous** if it must operate on the consumer thread's `ThreadLocal`.
4. Do not call `poll()`, `commitSync()`, `seek()`, or `close()` on `KafkaConsumer` when the container manages its lifecycle.
5. With `concurrency > 1`, expect multiple independent stopping events per child consumer.
6. Use `ConsumerAwareRebalanceListener` for partition revoke/assign; use `ContainerStoppedEvent` for whole-container state.
7. Cleanup must be fast, idempotent, observable on errors, and never close resources shared with other consumers.
8. Do not rely on the event to guarantee shutdown actions when the JVM crashes hard or a pod is killed ungracefully.
9. Combine the event with committed offsets, lag, stop reasons, and deployment timelines when diagnosing issues.
10. Test stop, restart, rebalance, pause/resume, and sync/async multicasters before relying on the event for production cleanup.

**Conclusion:** `ConsumerStoppingEvent` is a valuable lifecycle hook for Spring Kafka to announce that **the consumer thread is preparing to terminate**. It is well suited for fast, accurate cleanup of thread-bound resources alongside operational logs and metrics. Safety comes from running on the right thread, avoiding interference with the `KafkaConsumer` the container is closing, and keeping record processing, offset commits, rebalances, and crash recovery decoupled.
