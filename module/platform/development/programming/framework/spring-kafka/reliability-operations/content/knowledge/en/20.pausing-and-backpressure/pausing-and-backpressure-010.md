# Do Not Call stop on the Consumer Thread

In Spring Kafka, a listener container manages the lifecycle of `KafkaConsumer`: creating the consumer, calling `poll`, delivering records to the listener, handling errors, committing offsets, and closing the consumer when needed. When a system needs to shed load or halt consumption, the application can request **pause** or **stop** on the listener container. The two operations are not the same; in particular, **never call `container.stop()` directly on the consumer thread** executing the listener or a container callback.

This advice is a **thread and lifecycle safety rule**, not a Java syntax rule. The consumer thread is what the container needs to keep running so it can finish current steps and exit the poll loop. If that same thread executes the stop operation itself, it may wait on itself or conflict with the shutdown sequence, risking hangs, incomplete shutdowns, or indeterminate offset/transaction state.

In the Spring Kafka Reliability Operations module, the proper design is: **distinguish temporary backpressure from actual shutdown**, use `container.pause()/resume()` for temporary throttling; when stopping is truly required, **offload the stop request to an executor/lifecycle coordinator running on a separate thread**, then observe the stop outcome and manage controlled restarts.

## 1. What does the consumer thread do?

`KafkaConsumer` is not designed for arbitrary concurrent access across multiple threads. Spring Kafka places the consumer inside a listener container and dedicates a thread to drive the poll loop.

~~~text
Spring Kafka listener container
          |
          v
    Consumer thread
          |
          +-- consumer.poll()
          |
          +-- invoke @KafkaListener
          |
          +-- invoke CommonErrorHandler (on error)
          |
          +-- handle acknowledgement / offset commit
          |
          +-- rebalance callbacks
          |
          +-- poll again or exit when container stopping
~~~

With synchronous **record listeners**, the `@KafkaListener`-annotated method is normally invoked on the consumer thread. With synchronous batch listeners, the batch callback typically also runs on that poll/lifecycle thread. Many Spring Kafka lifecycle events and rebalance callbacks are emitted on this thread as well.

This means the following code looks ordinary at first glance, yet attempts to control the container itself from inside the very thread the container needs to finish its lifecycle:

~~~java
@KafkaListener(id = "orders-listener", topics = "orders")
public void onOrder(OrderEvent event) {
    if (maintenanceRequired(event)) {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        container.stop(); // DO NOT call directly on the consumer thread.
    }
}
~~~

The issue is not looking up the container via `KafkaListenerEndpointRegistry`, but **which thread invokes `stop()`** while the listener container is still inside a record-processing callback.

## 2. Why is calling stop() directly risky?

Stop is a lifecycle state transition. Depending on Spring Kafka version and container type, stopping can involve marking state, finishing in-progress records, flushing pending commits, closing `KafkaConsumer`, releasing threads, and emitting events.

A risky sequence:

~~~text
Consumer thread C
      |
      v
Kafka poll receives record
      |
      v
@KafkaListener.onOrder()
      |
      v
container.stop() directly on C
      |
      +-- lifecycle needs consumer loop to terminate
      |
      +-- consumer loop cannot terminate yet
      |   because C is still inside stop() / listener callback
      |
      v
Risk of self-wait, timeout, out-of-order shutdown
~~~

One should not claim every version and every `stop()` overload always deadlocks; implementations may include safeguards against self-waiting. However, **relying on implementation details to call `stop()` on the consumer thread is a fragile design**. Behavior can vary by container type, concurrency, callbacks, and Spring Kafka version.

Beyond blocking the thread, stopping at the wrong boundary complicates knowing whether the listener finished side effects, whether pending offsets committed, and whether the active Kafka transaction committed or aborted.

That is why the consumer thread should be treated as the place to **signal the need to stop**, not the place to execute the entire stop procedure itself.

## 3. Places where stop can accidentally run on the consumer thread

Locations requiring special care:

| Call site | Why might it run on the consumer thread? | Approach |
|---|---|---|
| **@KafkaListener** | Container invokes the listener inside the poll loop | Only call `requestStop` and hand off to a separate executor |
| **CommonErrorHandler** | Handler runs on the container's error-handling path | Use framework-supported container-stopping mechanisms or offload stop |
| **ConsumerAwareRebalanceListener** | Revoke/assign callbacks run during poll/rebalance | Do not stop directly; let callback finish quickly |
| **ListenerContainerIdleEvent listener** | Spring events may publish synchronously on the consumer thread | Do not stop directly in handler; switch threads |
| **ConsumerPausedEvent/ConsumerResumedEvent listener** | Events may arrive from lifecycle threads | Do not execute synchronous stop inside callbacks |
| **Container-attached interceptors/callbacks** | May execute on the consumer thread | Avoid lifecycle operations that wait on the current callback |

An `@EventListener` does not automatically run on a separate thread. With a synchronous `ApplicationEventMulticaster`, event handlers normally execute on the publisher's thread. Thus, **moving `stop()` into an `@EventListener` does not automatically solve the problem**.

If the application configures an asynchronous event multicaster, verify actual thread dispatching; never skip thread-safety rules assuming "event listeners are usually async." An application-managed coordinator/executor provides consistent behavior.

## 4. Stop and pause serve different purposes

This is the first decision to make when facing backpressure.

| Aspect | `container.pause()` | `container.stop()` |
|---|---|---|
| Consumer group membership | Typically retained while container keeps polling | Consumer closes/leaves group, may trigger rebalance |
| Continues polling | Container can keep polling to stay in group | Stops polling once shut down |
| New records to listener | Temporarily suspended once pause takes effect | Halts as container stops per lifecycle |
| Recovery | `container.resume()` | `container.start()` after stopping |
| Purpose | Throttle load or wait for dependency recovery | Shutdown, maintenance, config/lifecycle changes |
| Partition ownership impact | Does not surrender partitions merely by pausing | May transfer ownership to other consumers |
| Cost | Typically lighter, no forced rebalance | Incurs startup/shutdown and group coordination |

If a database connection pool saturates for a few seconds, `pause` usually fits better than `stop`. If the service must halt message intake entirely for shutdown, configuration changes, or extended maintenance, `stop` may make sense.

**Pause does not guarantee the listener stopped instantaneously.** Pause requests take effect at poll boundaries or per `pauseImmediate` configuration; observe actual state instead of treating a `pause()` call as proof all processing halted.

## 5. How to pause/resume for backpressure

Spring Kafka exposes the container control API:

~~~java
@Service
public class KafkaBackpressureControl {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaBackpressureControl(
            KafkaListenerEndpointRegistry registry) {
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
~~~

The **pause()** and **resume()** methods are container control APIs designed to request state transitions; they differ from calling `KafkaConsumer.pause()/resume()` directly on arbitrary threads. The container pauses/resumes the consumer at an appropriate point.

To inspect state:

- **isPauseRequested()** reflects that the container holds a pause request.
- **isConsumerPaused()** reflects the actual paused state per container semantics.
- Pause/resume events can assist in observing state transitions.

Do not equate **pause requested** with **pause effective**. Between those two instants, the listener may still process already-polled records.

### Pausing a single partition instead of the whole container

When one partition hits a hot dependency or needs key-based throttling, Spring Kafka provides partition-level pause/resume APIs:

~~~java
TopicPartition partition = new TopicPartition("orders", 2);

MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null && container.isRunning()) {
    container.pausePartition(partition);
}

// When recovery conditions are met:
if (container != null && container.isRunning()) {
    container.resumePartition(partition);
}
~~~

This API applies only when the partition belongs to an assignment the container can control; with concurrent containers, understand how Spring Kafka routes across child consumers. Never assume a partition remains on the same child consumer after a rebalance.

## 6. pauseImmediate and stopImmediate

Two easily confused options with distinct meanings:

- **pauseImmediate**: affects when the container stops delivering records after a pause request, when supported by the version.
- **stopImmediate**: affects when the listener container stops processing records from the current poll after receiving a stop request, when supported by the version.

Configuration example:

~~~java
factory.getContainerProperties().setPauseImmediate(true);
factory.getContainerProperties().setStopImmediate(true);
~~~

In Spring Kafka versions supporting these properties, immediate settings can make the container stop after the current record rather than finishing all records fetched in the poll. However, **immediate does not mean interrupting business code mid-flight**, nor does it guarantee no records remain dispatched to an async worker.

When the container retains undelivered records in memory during pause, account for memory pressure and container lifecycle. Upon stop/restart, unprocessed records must be re-read per committed offsets and container semantics.

**Enabling `stopImmediate` does not make calling `stop()` directly on the consumer thread safe.** The root issue is which thread runs the lifecycle operation; the immediate flag only changes how the container stops delivering records.

## 7. Safe pattern: decouple the stop request from the consumer thread

A straightforward design is a **KafkaStopCoordinator**. The consumer thread only calls `requestStop()`; the coordinator dispatches the actual work onto a separately managed executor.

~~~text
Consumer thread
      |
      v
@KafkaListener
      |
      +-- process record
      |
      +-- detect need to stop
      |
      v
stopCoordinator.requestStop("orders-listener")
      |
      v
Lifecycle executor queue
      |
      v
Lifecycle thread (distinct from consumer thread)
      |
      +-- look up container
      +-- container.stop()
      +-- record outcome / alert
~~~

Benefits:

1. The consumer thread never executes synchronous shutdown on itself.
2. Provides a central place to control restarts, backoff, deduplication, and logging.
3. The lifecycle executor can bound thread counts and queue capacity.
4. Distinguishes intentional stops from error-driven stops.
5. Simplifies testing thread ownership and final state.

The coordinator must handle **duplicate requests**, **executor capacity exhaustion**, and **containers already stopped before the task runs**.

## 8. Creating a dedicated lifecycle executor

Spring configuration example:

~~~java
@Configuration
public class KafkaLifecycleExecutorConfiguration {

    @Bean("kafkaLifecycleExecutor")
    public ThreadPoolTaskExecutor kafkaLifecycleExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("kafka-lifecycle-");
        executor.initialize();
        return executor;
    }
}
~~~

The numbers 2/4/64 are illustrative; a small service may need fewer workers. What matters is having a **dedicated executor for lifecycle**, never reusing the very consumer executor being stopped, and never using an unbounded queue that risks piling up stop/start commands.

If the lifecycle executor saturates, a `requestStop` may be rejected. For critical operational commands, add logging and alerts or an alternate control path; never silently treat a stop as successful when the task was rejected.

Never spawn a raw `Thread` manually per failing record. Coalesce and coordinate stop requests per container ID.

## 9. Example KafkaStopCoordinator

~~~java
@Service
public class KafkaStopCoordinator {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaStopCoordinator.class);

    private final KafkaListenerEndpointRegistry registry;
    private final TaskExecutor lifecycleExecutor;
    private final Set<String> pending = ConcurrentHashMap.newKeySet();

    public KafkaStopCoordinator(
            KafkaListenerEndpointRegistry registry,
            @Qualifier("kafkaLifecycleExecutor") TaskExecutor lifecycleExecutor) {
        this.registry = registry;
        this.lifecycleExecutor = lifecycleExecutor;
    }

    public void requestStop(String listenerId) {
        if (!pending.add(listenerId)) {
            return; // Stop request already in progress.
        }

        try {
            lifecycleExecutor.execute(() -> {
                try {
                    MessageListenerContainer container =
                            registry.getListenerContainer(listenerId);

                    if (container == null) {
                        log.warn("Listener container not found: {}", listenerId);
                        return;
                    }

                    if (container.isRunning()) {
                        log.info("Stopping listener container {}", listenerId);
                        container.stop();
                    }
                }
                catch (RuntimeException ex) {
                    log.error("Unable to stop listener {}", listenerId, ex);
                    // Emit alert or route into managed recovery.
                }
                finally {
                    pending.remove(listenerId);
                }
            });
        }
        catch (TaskRejectedException ex) {
            pending.remove(listenerId);
            log.error("Lifecycle executor rejected stop for {}", listenerId, ex);
            // Do not treat this request as a successful stop.
        }
    }
}
~~~

This pattern uses standard Spring Kafka and Spring Task APIs. Supply imports, beans, and logging appropriate for your application.

In the example, `pending` prevents enqueueing dozens of stop commands for the same listener while an earlier command is still running. However, once the task completes, **calling `stop()` does not guarantee every child consumer has stopped** if the lifecycle implementation is asynchronous. If definite final state is required, monitor container events or use a supported `stop` API completion callback.

When production requires repeated stop/start cycles, the coordinator should use a **state machine** rather than just a `pending` flag, avoiding a new start request executing before an earlier stop completes.

## 10. Listener issues stop request only after processing completes

Example listener with a maintenance condition:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;
    private final KafkaStopCoordinator stopCoordinator;
    private final MaintenanceGate maintenanceGate;

    @KafkaListener(
            id = "orders-listener",
            topics = "orders",
            groupId = "orders-service")
    public void onOrder(OrderEvent event) {
        orderService.process(event);

        if (maintenanceGate.shouldStopAfterCurrentRecord()) {
            stopCoordinator.requestStop("orders-listener");
        }
    }
}
~~~

In this example, `requestStop` appears **only after business processing of the record succeeds**. That reduces the risk of returning normally while a record remains unprocessed.

However, offset commit may occur **after the listener returns**, depending on `AckMode` and transaction mode. Do not conclude the broker committed the offset simply because `requestStop` ran after `process()`. Assume the record may be redelivered if the container stops/crashes before commit, and protect side effects with idempotency.

If the stop condition triggers **before** processing the record, never simply call `requestStop` and return as a success. Instead, pause before accepting more records, or let the record fail under the appropriate error-handling/acknowledgment policy.

## 11. Mistake: stopping and returning on an unprocessed record

Dangerous example:

~~~java
@KafkaListener(id = "orders-listener", topics = "orders")
public void handle(OrderEvent event) {
    if (downstreamUnavailable()) {
        stopCoordinator.requestStop("orders-listener");
        return; // May be treated as successful processing.
    }

    process(event);
}
~~~

For a record listener with `AckMode.RECORD`, returning normally can cause the container to consider the record processed and commit its offset per policy. If `process(event)` never ran, the record risks being skipped functionally.

Better approaches:

- Throttle intake **before delivering more records** via `container.pause()`.
- If a record was already received and a dependency failed, throw a retryable exception so the error handler manages retry/recovery.
- If using manual acknowledgment, acknowledge only after business work actually succeeds.
- If stopping for maintenance, issue the stop request while still letting business errors flow through the proper error/rollback path.

Stop is not a substitute for determining whether a record succeeded.

## 12. ListenerContainerIdleEvent and safe stopping

A practical case: an application wants to stop a consumer after receiving no messages for a configured period. Spring Kafka emits **ListenerContainerIdleEvent** when an idle event interval is configured.

This event may be published synchronously on the consumer thread. Therefore, avoid:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");
    container.stop(); // Unsafe if event handler runs on the consumer thread.
}
~~~

Instead:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    if (event.getListenerId().startsWith("orders-listener")) {
        stopCoordinator.requestStop("orders-listener");
    }
}
~~~

The `startsWith` pattern only illustrates filtering events; **never use an insufficiently distinct prefix** if the application has similarly named listener IDs. With concurrent containers, child container IDs can carry suffixes; design accurate child/parent mapping against real IDs.

An idle event does not automatically mean a service should stop. A topic having no records for a few minutes can be normal. Combine with business rules, maintenance states, or operational schedules before requesting stop.

## 13. Registering a post-stop callback

Some Spring Kafka container APIs support **stop(Runnable callback)** to invoke a callback once stopping completes per lifecycle.

~~~java
lifecycleExecutor.execute(() -> {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

    if (container != null && container.isRunning()) {
        container.stop(() ->
                log.info("Listener orders-listener has stopped"));
    }
});
~~~

Check the overload and callback semantics of your Spring Kafka version. The callback should do brief work such as logging, updating state, or signaling; for complex operations, continue coordinating through the lifecycle coordinator.

Never immediately restart the container inside a callback without verifying stopping truly completed. A race between stop and start can yield unpredictable lifecycle outcomes, especially with concurrent containers.

## 14. ConcurrentMessageListenerContainer: stop parent or child?

A listener with concurrency greater than 1 typically runs via one parent `ConcurrentMessageListenerContainer` and multiple child `KafkaMessageListenerContainer` instances.

~~~text
Parent: orders-listener (concurrency=3)
    |
    +-- child 0 -> consumer A -> P0, P1
    |
    +-- child 1 -> consumer B -> P2, P3
    |
    +-- child 2 -> consumer C -> P4, P5
~~~

When looking up the container from `KafkaListenerEndpointRegistry` using the ID declared on `@KafkaListener`, the application normally operates on the parent container. Stopping the parent coordinates stopping that listener's child consumers. If extracting the source container directly from a lifecycle event, it may be a child container; confirm the true target.

Therefore:

1. Clarify whether the requirement is stopping the **entire listener** or stopping **one child consumer**.
2. Use a stable listener ID for listener-level control logic.
3. Never share a single `KafkaConsumer` object across children.
4. Never statically map partitions to child indices, as assignments change on rebalance.
5. Log parent/child IDs and affected partitions in operations.

When the goal is throttling a single partition, **`pausePartition`** usually has a cleaner blast radius than stopping the entire parent container.

## 15. Stop causes rebalances; pause usually does not

When a container stops completely, the consumer stops polling and may leave the group. Partitions previously owned by that consumer are reassigned to remaining members if the group stays active.

~~~text
Before:
  Consumer A -> P0, P1
  Consumer B -> P2, P3

A stops:
  Consumer A leaves group
  Group rebalances

After:
  Consumer B -> P0, P1, P2, P3
~~~

If the application only wants to wait briefly for a database recovery, stopping can trigger unnecessary rebalances, shift load to another instance, and increase duplicate-processing risk.

With pause:

~~~text
Consumer A -> P0, P1 (retains ownership)
Consumer A pauses
Consumer A keeps polling to maintain membership
Consumer A resumes once dependency is healthy
~~~

Pause only throttles delivering records to the listener rather than yielding partitions. Thus pause is better suited for temporary backpressure halts.

Note: pause does not guarantee the consumer keeps group membership forever if the application itself fails to poll on time for other reasons. Manage listener time, worker saturation, and `max.poll.interval.ms`.

## 16. Stopping a container is not instantaneous

A stop command may need to wait for the currently processing record and ongoing container tasks to finish. With `stopImmediate=false`, containers in some versions may finish records already received from the prior poll before stopping. With `stopImmediate=true`, they may halt further delivery after the current record.

~~~text
consumer.poll() returns record offsets 100..109
        |
        v
Listener is processing offset 100
        |
        +-- receives requestStop()
        |
        v
Container stops per StopImmediate/implementation policy
        |
        +-- may finish already-polled records
        +-- or stop after current record
        |
        v
Consumer closes, partitions handed off
~~~

Therefore, when an admin API returns "stop requested," do not display "stopped" without a signal confirming the final state.

Define explicit states:

~~~text
RUNNING -> STOP_REQUESTED -> STOPPING -> STOPPED
                           |
                           +-- STOP_FAILED / RETRY_NEEDED
~~~

Exact transition order is governed by the coordinator and container lifecycle. If the application also supports `START_REQUESTED`, handle start requests arriving while `STOPPING`.

## 17. Offset commits and stop

Kafka committed offsets represent the **next** position the consumer group will read. For a record at offset 40, successful processing usually commits offset 41.

~~~text
P0:
  offset 39 -> DONE
  offset 40 -> DONE
  offset 41 -> IN_FLIGHT
  offset 42 -> QUEUED

Safe offset if only 39 and 40 completed:
  41
~~~

If a stop occurs while offset 41 has not finished, the application must not commit offset 43 merely because records were fetched or enqueued. Doing so can skip unprocessed records.

With synchronous listeners, the container and `AckMode` normally manage progress more cleanly. With asynchronous processing, guard against offset gaps:

- Acknowledge only records that truly completed.
- Commit only up to the partition's **last contiguous completed offset**.
- Never treat an enqueued task as processed.
- On stop, plan a deadline-bounded task drain or let uncommitted records replay.
- Protect side effects with event IDs/idempotency when records are reprocessed.

The stop coordinator does not automatically know which records succeeded. It cannot replace offset management and business semantics.

## 18. Manual acknowledgment with requestStop

With `AckMode.MANUAL` or `MANUAL_IMMEDIATE`, the listener can accept `Acknowledgment` and acknowledge after processing:

~~~java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        containerFactory = "manualAckFactory")
public void handle(
        OrderEvent event,
        Acknowledgment ack) {

    orderService.process(event);
    ack.acknowledge();

    if (maintenanceGate.shouldStopAfterCurrentRecord()) {
        stopCoordinator.requestStop("orders-listener");
    }
}
~~~

This example is valid only if `manualAckFactory` configures the matching `AckMode`. **`acknowledge()` is not a promise that the commit finished on the broker in every mode and on every thread**. With `MANUAL`, commits may happen afterward; with `MANUAL_IMMEDIATE`, semantics differ and depend on the thread calling acknowledge.

Even after acking, a process crash before the commit finishes can still cause record redelivery. Consumer design must tolerate at-least-once delivery and idempotency.

Never call ack on an unprocessed record merely because the container is about to stop.

## 19. Transactional listeners: stop must respect transaction boundaries

With Kafka consume-process-produce transactions, the listener container opens a Kafka transaction and includes consumed offsets in the transaction alongside output records.

~~~text
Kafka container BEGIN transaction T1
       |
       +-- consume orders.input/P1@50
       +-- produce orders.output
       |
       +-- listener completes
       |
       +-- sendOffsetsToTransaction(P1 -> 51)
       |
       v
COMMIT T1
~~~

If the listener throws an exception, the transaction can abort. If a stop/race/shutdown occurs before commit finishes, input records may be redelivered from committed offsets.

Never call `consumer.commitSync()` inside a listener or shutdown callback to "mark done" while using Kafka transactions. Offsets must be coordinated by the container/transaction manager alongside outputs.

Furthermore, a Kafka transaction **does not roll back database or HTTP side effects**. If a listener updates a DB and then stops/crashes before Kafka commits, the record may be reprocessed. Use idempotency keys, unique constraints, or an outbox when business guarantees are required.

For transactional listeners, let transaction boundaries complete or abort along container-supported paths rather than closing the consumer yourself inside a business callback.

## 20. Stopping from an error handler: distinguish error types

A `CommonErrorHandler` can be invoked when a listener throws an exception. Because the handler sits on the container's processing path, it is not a safe place to arbitrarily call `container.stop()` yourself.

Anti-pattern example:

~~~java
public void handleOne(
        Exception exception,
        ConsumerRecord<?, ?> record,
        Consumer<?, ?> consumer,
        MessageListenerContainer container) {

    container.stop(); // Do not stop synchronously on the consumer thread.
}
~~~

Some Spring Kafka versions provide built-in error handlers designed to stop containers on severe errors, such as APIs in the container-stopping error handler family. When this is an explicit requirement, prefer the Spring Kafka mechanism built for that case and check your version's semantics.

Do not confuse:

- Transient business error: retry/backoff then recovery.
- Unrecoverable data error: DLT or non-retryable handling.
- Overloaded dependency: pause/backpressure or circuit breaker.
- Severe infrastructure failure requiring halt: stop the container via a safe lifecycle path.

In particular, having an error handler swallow an exception and return can make the container treat the record as processed under some configurations. If the record has not recovered cleanly, preserve proper exception/ack/offset semantics to prevent data loss.

## 21. Rebalance callbacks are not where to stop directly

The `onPartitionsRevoked`/`onPartitionsAssigned` callbacks normally execute during polling and rebalancing, so they should also stay brief.

~~~text
Consumer poll thread
      |
      v
onPartitionsRevoked(P1, P2)
      |
      +-- bounded flush/checkpoint
      +-- release state for P1, P2
      |
      v
Return control to Kafka rebalance
~~~

Calling stop directly here makes the application initiate lifecycle shutdown mid-handoff, creating reentrancy and delaying group coordination. Do not use a revoke callback to shut down the entire listener simply because assignments changed.

If business policy genuinely requires stopping after a rebalance event, the callback can record a signal and dispatch a request via the lifecycle coordinator **after leaving the consumer thread**. Still, remember normal rebalances happen during deploys/scaling and do not mean the consumer should shut down.

When partitions are already lost, do not try committing offsets as the old owner merely to serve shutdown.

## 22. Which signals should drive backpressure?

Stopping the whole container is a rather heavy hammer. For backpressure, define clear thresholds:

| Signal | Appropriate response |
|---|---|
| Worker queue exceeds high watermark | Request pause |
| Worker queue drops below low watermark | Request resume |
| Database pool temporarily near exhaustion | Pause, throttle concurrency/throughput |
| Downstream returns brief HTTP 429/503 | Backoff, pause, or error handler depending on ordering |
| DLT publish fails and cannot recover | Alert, evaluate controlled stop |
| Listener needs prolonged maintenance | Stop via lifecycle executor |
| Subscriptions/configuration must change | Stop and restart per deployment policy |

Do not pause/resume repeatedly whenever a queue oscillates around one threshold. Use **hysteresis**:

~~~text
Worker queue capacity = 1000

Queue >= 800 -> PAUSE
Queue <= 300 -> RESUME

300 < Queue < 800 -> keep current state
~~~

Thresholds are illustrative only. Set them based on throughput, latency, memory, and dependency load capacity.

Pause does not make processing faster; it lowers the rate of admitting more work into the system. If a consumer has a large backlog, Kafka lag grows while paused and drains gradually upon resume.

## 23. Implementing a pause controller with hysteresis

A simple controller can run from a scheduler or monitoring thread instead of letting each record decide to stop:

~~~java
@Component
public class QueueBackpressureMonitor {

    private final KafkaListenerEndpointRegistry registry;
    private final WorkQueueMetrics queueMetrics;
    private boolean pauseRequested;

    @Scheduled(fixedDelay = 1_000L)
    public synchronized void check() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null || !container.isRunning()) {
            return;
        }

        int depth = queueMetrics.pendingJobs();

        if (!pauseRequested && depth >= 800) {
            container.pause();
            pauseRequested = true;
        }
        else if (pauseRequested && depth <= 300) {
            container.resume();
            pauseRequested = false;
        }
    }
}
~~~

This example requires scheduling enabled and a `WorkQueueMetrics` bean. If multiple code paths can pause/resume the same container, a local boolean is insufficient. Production needs **a shared control state source** distinguishing pause reasons (backpressure, maintenance, circuit breaker) so one subsystem does not resume while another still requires pausing.

In multi-replica systems, queue depth per instance can differ. A local monitor throttles only its own instance's container; there is no need to pause the entire cluster if only one pod is overloaded.

## 24. Risks when the lifecycle executor saturates

Offloading stop to another thread is necessary, yet insufficient if the executor is poorly operated.

Scenarios:

- **Queue full**: `requestStop` is rejected and the container keeps running.
- **Stuck stop task**: lifecycle threads can no longer process new commands.
- **Duplicate storms**: thousands of stop tasks target the same container simultaneously.
- **App shutdown**: the lifecycle executor may be destroyed before finishing pending requests.
- **Concurrent stop/start**: the container transitions out of the order operators intended.

Mitigations:

1. Keep the executor dedicated and bounded.
2. Coalesce requests by listener/container ID.
3. Log rejected tasks and alert on critical commands.
4. Track executor queue depth, task duration, and rejected counts.
5. Use a coordinator with a state machine when both stop and start exist.
6. Never allow unbounded lifecycle operations; apply timeouts/watchdogs at the coordination layer.
7. Check app shutdown ordering so the lifecycle executor stays active through required stop phases.

Never use `CallerRunsPolicy` to handle lifecycle executor rejections if it causes **the consumer thread itself to run the stop task**. That reintroduces the exact original failure mode.

## 25. Restarting after stop: do not just call resume()

When a container is only paused, `resume()` can continue operating on existing assignments. After a stop, however, the consumer has shut down and may have left the group.

~~~text
RUNNING
   |
   +-- pause() --> PAUSED
   |                 |
   |                 +-- resume() --> RUNNING
   |
   +-- stop()  --> STOPPING --> STOPPED
                                      |
                                      +-- start() --> RUNNING
~~~

For a stopped container, calling `resume()` does not replace `start()`. On start, a new `KafkaConsumer` joins the group and receives fresh partition assignments. Only after start and assignment succeed should the consumer be considered recovered.

Do not start a container immediately inside an event indicating stop was requested. Wait for completed stop or a stable lifecycle state. If policy auto-restarts, add backoff to avoid continuous stop–start–rebalance loops.

In systems using `KafkaListenerEndpointRegistry`, start/stop can be controlled by **listener ID**, provided you select the container managed by the registry. Manually created containers outside the registry may require separate bean/reference management.

## 26. Graceful shutdown from the application lifecycle

When a Spring Boot application shuts down, the framework runs lifecycle stop for managed beans/containers. Normally **you do not need to call `stop()` yourself from `@KafkaListener` on shutdown signals**.

If custom quiescing is needed:

1. Stop accepting new ingress requests.
2. Pause Kafka listeners if in-flight tasks must drain.
3. Wait for in-flight business work within a deadline.
4. Request stop via the appropriate lifecycle manager/executor.
5. Observe the container actually stopped.
6. Finish non-Kafka cleanup and close resources.

Never block shutdown callbacks indefinitely, as Kubernetes termination grace periods or orchestrator timeouts can expire. Processes can be killed without running cleanup; hence proper offset commits and idempotency remain mandatory safeguards.

A clean stop does not guarantee zero redeliveries. If the final commit did not finish or a transaction aborted, Kafka can replay records; that is normal behavior of at-least-once/transactional processing.

## 27. Observing lifecycle and ConsumerStoppedEvent

Spring Kafka provides application events for consumer/container lifecycles. You can observe **ConsumerStoppedEvent** to distinguish normal stops from error-induced stops.

~~~java
@EventListener
public void onConsumerStopped(ConsumerStoppedEvent event) {
    log.info(
            "Kafka consumer stopped: reason={}, source={}",
            event.getReason(),
            event.getSource());
}
~~~

With concurrent containers, child consumers may emit separate events. Match listener/container IDs to know at what scope stopping completed; do not see one `ConsumerStoppedEvent` and conclude all child consumers stopped.

Operational logs should record:

~~~text
action=stop_requested
listenerId=orders-listener
requestSource=backpressure-controller
consumerThread=orders-listener-0-C-1
executionThread=kafka-lifecycle-1
stopReason=maintenance
transition=STOPPING
~~~

This is an illustrative application log format, not a built-in Spring Kafka format. When `requestStop` is called from a consumer thread, logs should confirm the actual stop ran on **a different thread**.

On unexpected stops, distinguish `Reason.NORMAL` from authentication, fencing, missing-offset, or other lifecycle errors per reasons supported by your Spring Kafka version. Do not auto-restart every error class under one policy without root-cause analysis.

## 28. Monitoring for pause/stop/backpressure

Useful metrics:

- Counts of listener containers `RUNNING`, `PAUSED`, `STOPPING`, `STOPPED`.
- Pause/resume request counts and actual pause duration.
- Stop request counts, stop completions, and stop failures.
- Latency from stop requested to stopped.
- Lifecycle executor queue depth, rejections, and task latency.
- Consumer lag by topic/partition.
- Listener processing duration p95/p99 and in-flight task count.
- Rebalance count after stop/start.
- Offset commit failures and transaction aborts.
- Rapid stop/start transition counts within short windows.

Metrics should distinguish **desired state** from **observed state**. For example, sending a pause request does not mean the container has completely suspended. Sending a stop request does not mean the thread has closed.

Never put offsets, event IDs, or full exception messages into high-cardinality metric labels. Those details belong in structured logs and traces.

## 29. Testing that stop does not run on the consumer thread

### Test 1: requestStop from @KafkaListener

1. Start a Spring Kafka listener and send a record.
2. Have the listener succeed and call `stopCoordinator.requestStop()`.
3. Record the thread name in the listener and right before `container.stop()` inside the coordinator.
4. Assert the two threads are different.
5. Wait for the container to stop using a timeout-bounded condition.
6. Confirm no polling continues after stop completes.

### Test 2: idle event

1. Configure a suitably short idle event interval in the test.
2. Leave the listener container without records for a window.
3. Have the event handler only call `requestStop`, never stop directly.
4. Verify the lifecycle executor receives the stop task.
5. Verify the container stops without the consumer thread waiting on itself.

### Test 3: stop requested while processing a record

1. Listener receives a record and holds a dependency call via a test latch.
2. Another thread calls `requestStop`.
3. Observe stopping behavior per the container's `stopImmediate` and `AckMode`.
4. Release the dependency call.
5. Verify the record is committed or replayed according to semantics.
6. Confirm zero lost processing.

### Test 4: backpressure pause/resume

1. Drive worker queue depth past the high watermark.
2. Confirm the controller requests pause.
3. Confirm the consumer group retains assignments and the container keeps polling per design.
4. Lower queue depth below the low watermark.
5. Confirm resume and continued processing.
6. Confirm zero pause/resume flapping.

### Test 5: concurrent child containers

1. Create a listener with concurrency greater than 1.
2. Request stop by parent listener ID.
3. Confirm child containers stop per lifecycle.
4. Check that no duplicate stop tasks fire for individual children.
5. Restart and verify the group receives valid assignments.

### Test 6: lifecycle executor rejection

1. Use an executor with a tiny queue in the test.
2. Trigger a `TaskRejectedException` on `requestStop`.
3. Verify the coordinator logs/alerts on the failure.
4. Verify the container is not considered stopped when the task was rejected.
5. Verify it never falls back to running `stop()` on the consumer thread.

### Test 7: crash before offset commit

1. Listener completes the business side effect without committing the offset yet.
2. Stop the process or trigger a controlled transaction abort.
3. Start a new consumer.
4. Verify the record can be redelivered.
5. Verify idempotency prevents unwanted duplicate side effects.

Integration tests should use a Kafka test broker such as Testcontainers Kafka or EmbeddedKafka to observe real group assignments, consumer stops, commit/replay, and pause/resume. Do not merely mock `KafkaListenerEndpointRegistry` and conclude Kafka consumer lifecycle behavior is correct.

## 30. Common misconceptions

**Calling `container.stop()` inside `@KafkaListener` is safe because both belong to Spring.** False. The listener normally runs on the consumer thread and stop can interact with that thread's own shutdown.

**Moving `stop()` into `@EventListener` always runs it on another thread.** False. Spring application events can dispatch synchronously on the publishing thread.

**`stopImmediate=true` makes calling `stop()` on the consumer thread safe.** False. It only changes when record processing stops per container semantics.

**`container.pause()` is the same as `container.stop()`.** False. Pause usually keeps membership and polling; stop closes the consumer and can cause rebalances.

**Calling `pause()` means no listeners are running anymore.** False. Pause must take effect and already-polled records may still be processing.

**Calling `requestStop` means the container has stopped.** False. Wait for completion/final state observation.

**An `ExecutorService` alone suffices without deduplicating requests.** False. Multiple callbacks can queue multiple stop tasks and race with starts.

**`CallerRunsPolicy` is a safe fallback for the lifecycle executor.** False when the caller is the consumer thread; it can run `stop()` right on the thread you needed to avoid.

**Stopping before processing a record and returning guarantees the record will be re-read.** False. Returning normally can cause the container to mark processing successful per `AckMode`.

**Stop always guarantees all already-polled records complete.** False. Outcome depends on `stopImmediate`, listener model, acknowledgments, and in-flight tasks.

**Pausing a partition means yielding that partition to another consumer.** False. Pause usually retains ownership.

**A Kafka transaction rolls back the database too on stop.** False. Non-Kafka side effects need their own transactions/idempotency.

**Restarting a container after stop only needs `resume()`.** False. Resume applies to paused containers; stopped containers need `start()` per lifecycle.

## 31. Production adoption procedure

When a Spring Kafka application needs to throttle load or stop a listener:

1. Determine whether the goal is **temporarily pausing consumption** or **stopping lifecycle**.
2. Prefer `pause`/`resume` for short-term backpressure, preserving consumer group membership.
3. Use high/low watermarks and a unified controller to avoid continuous pause/resume oscillation.
4. When stopping is needed, never call it directly from `@KafkaListener`, error handlers, rebalance callbacks, or synchronous event handlers.
5. Create a dedicated lifecycle executor and a coordinator receiving `requestStop` by listener ID.
6. Bound concurrent stop requests and handle `TaskRejectedException`.
7. Decide whether stopping the parent or a child container is needed when concurrency exceeds 1.
8. Execute stop from a lifecycle thread distinct from the consumer thread and observe the stopped outcome.
9. Never acknowledge unprocessed records merely to make stopping faster.
10. With transactional listeners, let the container govern Kafka offset commit/abort inside the transaction.
11. With async processing, manage in-flight tasks, contiguous completed offsets, and deadline drains.
12. Ensure idempotency for records that may replay after stop/restart.
13. Design stateful restart policies with backoff to prevent stop/start/rebalance loops.
14. Monitor pause duration, stop duration, lag, rebalances, and commit failures.
15. Test stopping from listeners, idle events, executor rejections, crashes, and concurrent containers.

**Do not call stop on the consumer thread** is a rule that protects the Spring Kafka listener container lifecycle. The consumer thread should finish its callback and return control to the poll loop, while stop commands are executed by a lifecycle coordinator on a separate thread. When the issue is only temporary backpressure, **`pause`/`resume` is usually preferable to `stop`/`start`** because it avoids closing the consumer and triggering rebalances. Regardless of choice, ensure offsets/acknowledgments reflect truly processed records, avoid premature commits, and prepare for record redelivery on stops or restarts.
