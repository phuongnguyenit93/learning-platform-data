# ConsumerPausedEvent and ConsumerResumedEvent

In Spring Kafka, **ConsumerPausedEvent** and **ConsumerResumedEvent** are two **application events** reflecting that a Kafka consumer managed by a listener container **has actually been paused or resumed**. They are especially useful when an application uses pause/resume to implement **backpressure**, limit load on a database, wait for a dependency to recover, or control processing throughput during operations.

The most important point is distinguishing **a state-change request** from **a state that has taken effect**. When a thread calls **container.pause()**, Spring Kafka records the request and applies it at an appropriate point in the consumer's poll loop. Thus, the `pause()` method returning **does not mean all partitions are immediately paused at that instant**. `ConsumerPausedEvent` helps observe when the consumer is actually paused; `ConsumerResumedEvent` plays the corresponding role upon resuming.

These two events provide better lifecycle visibility, yet **they do not handle offsets, stop the consumer group, guarantee all business tasks are finished, or replace error handlers**. Using them properly requires combining an understanding of the `KafkaConsumer` poll loop, concurrent listener containers, per-partition pausing, thread safety, and actual processing state.

## 1. Why observe pause/resume?

Suppose the `inventory-service` consumes the `inventory.commands` topic and updates a database. When the database connection pool saturates, continuing to fetch and process more Kafka records increases latency, piles up threads waiting for connections, and eventually triggers cascading failures.

The application can request a pause:

~~~text
inventory.commands
        |
        v
Spring Kafka listener
        |
        v
Database connection pool
        |
        +-- normal load --> continue processing
        |
        +-- exceeds threshold --> container.pause()
                                  |
                                  v
                             Pause requested
                                  |
                                  v
                        Consumer actually paused
                                  |
                                  v
                         ConsumerPausedEvent
~~~

After the database stabilizes:

~~~text
Backpressure controller
       |
       v
container.resume()
       |
       v
Resume requested
       |
       v
Consumer actually resumed
       |
       v
ConsumerResumedEvent
       |
       v
Continue delivering records to listener
~~~

If you only log "pause called" and "resume called," operators do not know whether the request took effect, whether any child consumers have not changed state yet, or whether another thread reversed the request. Application events add the container's **observed state** perspective.

## 2. What does KafkaConsumer.pause() actually do?

At the Kafka client layer, **KafkaConsumer.pause(Collection<TopicPartition>)** suspends fetching/returning new records for the specified partitions per `KafkaConsumer` mechanics. **resume(Collection<TopicPartition>)** resumes consuming those partitions.

Pausing **is not** leaving the consumer group, does not clear assignments, and does not automatically commit offsets.

~~~text
Consumer A owns:
  orders/P0
  orders/P1

Pause orders/P1:
  P0 ownership -> still belongs to A
  P1 ownership -> still belongs to A

Polling:
  A keeps polling to maintain consumer group membership
  P0 can continue receiving records
  P1 temporarily delivers no new records
~~~

In Spring Kafka, control should normally go through **listener container.pause()/resume()** rather than grabbing `KafkaConsumer` and calling pause/resume directly from an external thread. `KafkaConsumer` is not thread-safe for arbitrary calls; the container coordinates requests onto the consumer thread.

Pausing throttles the pace of accepting new work. It **does not cancel an already-running database query**, roll back an already-sent HTTP request, or discard records already delivered to the listener before the pause took effect.

## 3. What do the two events reflect?

| Event | Observed condition | Operational meaning |
|---|---|---|
| **ConsumerPausedEvent** | Container paused the consumer per request/policy | Consumer transitioned to paused state for the announced partitions |
| **ConsumerResumedEvent** | Container resumed the consumer | Consumer resumed consuming the announced partitions |

The events include information on the relevant partitions, allowing the application to distinguish which consumer or partition set was affected.

Do not confuse these events with:

- **ConsumerStoppedEvent**: the consumer closed/ended its lifecycle.
- **ConsumerStartingEvent/ConsumerStartedEvent**: the consumer began its lifecycle.
- **ListenerContainerIdleEvent**: the container received no records per idle criteria.
- **onPartitionsRevoked**: the consumer yielded partition ownership due to a rebalance.
- **onPartitionsLost**: the consumer lost ownership.
- **BackOff/DefaultErrorHandler**: record retry or error-handling policies.

A paused consumer can still be running its poll loop and holding assignments. Therefore, **ConsumerPausedEvent is not ConsumerStoppedEvent**.

## 4. From pause requested to ConsumerPausedEvent

Spring Kafka manages pause changes on the consumer thread to avoid calling `KafkaConsumer` from arbitrary threads. A typical flow:

~~~text
Monitoring thread / REST admin / scheduler
          |
          v
container.pause()
          |
          +-- record pause requested
          |
          v
Consumer thread finishes current processing chunk
          |
          v
Poll loop applies consumer.pause(partitions)
          |
          v
Consumer is in paused state
          |
          v
Spring Kafka publishes ConsumerPausedEvent
~~~

The delay between **pause requested** and **paused event** depends on container state:

- Whether the listener is currently processing a long-running record.
- How many records a single poll fetched.
- Whether **pauseImmediate** is enabled.
- Whether the consumer is rebalancing or running error handling.
- Whether the container is a single consumer or a concurrent container.
- The Spring Kafka version and its lifecycle details.

Therefore, do not treat `container.pause()` returning as a synchronous barrier guaranteeing all listener callbacks have stopped. For observational needs, **listening to events and checking container state** are complementary.

## 5. From resume requested to ConsumerResumedEvent

When `container.resume()` is called, the container records the request and executes `consumer.resume(...)` at an appropriate moment on the consumer thread.

~~~text
Monitoring sees dependency healthy
          |
          v
container.resume()
          |
          v
Resume requested
          |
          v
Consumer thread applies resume
          |
          v
Spring Kafka publishes ConsumerResumedEvent
          |
          v
Consumer can continue receiving records
~~~

**ConsumerResumedEvent does not mean the first business record after resuming succeeded**. The event reflects resumed consumption readiness, whereas processing results must be measured via listener success rate, offset progress, consumer lag, and business metrics.

On a low-traffic topic, no new records may arrive right after `ConsumerResumedEvent`. That is not a sign that resume failed if the consumer is already permitted to consume.

If another controller requests pause again right after resume, the application can observe back-to-back events. Record the **pause reason** and govern decision ownership to prevent oscillation.

## 6. Configuring a Kafka listener that can pause/resume

A typical listener:

~~~java
@Component
public class InventoryCommandListener {

    private final InventoryService inventoryService;

    public InventoryCommandListener(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @KafkaListener(
            id = "inventory-listener",
            topics = "inventory.commands",
            groupId = "inventory-service")
    public void onCommand(InventoryCommand command) {
        inventoryService.apply(command);
    }
}
~~~

To pause/resume, the application retrieves the listener container from **KafkaListenerEndpointRegistry** by listener ID:

~~~java
@Service
public class InventoryConsumerControl {

    private final KafkaListenerEndpointRegistry registry;

    public InventoryConsumerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void requestPause() {
        MessageListenerContainer container =
                registry.getListenerContainer("inventory-listener");

        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void requestResume() {
        MessageListenerContainer container =
                registry.getListenerContainer("inventory-listener");

        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
~~~

These methods **send a request** to the container. If the registry lacks the listener ID, check bean registration, `autoStartup`, and how the container was created. A listener container created manually outside the registry may need to be managed via its own bean/reference.

**Never create a new KafkaConsumer just to pause a running consumer.** A new consumer has a different identity, assignment, and lifecycle.

## 7. Listening for ConsumerPausedEvent with @EventListener

A Spring application context can receive events published by Spring Kafka. A simple observer:

~~~java
@Component
public class KafkaPauseResumeObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPauseResumeObserver.class);

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
                "Kafka consumer paused, partitions={}",
                event.getPartitions());
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka consumer resumed, partitions={}",
                event.getPartitions());
    }
}
~~~

This snippet illustrates the Spring application event pattern. Include imports from Spring Kafka's listener events package, `@EventListener`, and logging matching your project.

The event provides context on the publishing container and associated partitions. To distinguish multiple listener containers, inspect **event source/container** via the API of your Spring Kafka version, combined with listener ID and child container identity.

If the entire application has only one listener, logging partitions may suffice. With dozens of listeners and concurrent containers, include the event source to avoid confusion.

## 8. Application events and execution threads

In Spring, **@EventListener does not automatically mean asynchronous execution**. With the default synchronous `ApplicationEventMulticaster`, callbacks usually run on **the thread that published the event**. With Spring Kafka, many consumer/container events are published on the consumer thread.

~~~text
Consumer thread
     |
     +-- apply consumer.pause()
     |
     +-- publish ConsumerPausedEvent
     |
     +-- invoke @EventListener synchronously
     |
     +-- return to poll/lifecycle loop
~~~

Therefore, event listeners should:

- Write concise logs.
- Update lightweight metric counters/gauges.
- Store observational state in thread-safe structures.
- Signal another coordinator if time-consuming work is needed.

Do not:

- Call external APIs that may hang.
- Run long database transactions.
- Wait on a `CompletableFuture` without a timeout.
- Call `container.stop()` synchronously directly from an event callback on the consumer thread.
- Use a `KafkaConsumer` obtained from the event to poll/commit from another thread.

If the event multicaster is configured to run asynchronously, do not assume the event handler still runs on the consumer thread. Enforce thread safety and never use thread-sensitive `KafkaConsumer` references inside async callbacks.

## 9. Why not stop the container from an event handler?

An anti-pattern:

~~~java
@EventListener
public void onPaused(ConsumerPausedEvent event) {
    MessageListenerContainer container = findContainer(event);
    container.stop();  // Avoid calling stop directly in a callback that may run on the consumer thread.
}
~~~

In the example, `findContainer` is an application helper, not a built-in Spring Kafka API.

Stop is a different lifecycle operation from pause. It may require the container to finish its poll loop, close the consumer, commit pending offsets, and hand over partitions. If a callback running on the consumer thread calls synchronous stop, it risks reentrant shutdown, blocking the consumer thread, or creating unpredictable lifecycle states.

If the system genuinely needs to stop after pause takes effect, send the request to a **separate lifecycle executor/coordinator**, and let that thread drive stop. Never use an event listener as the place to directly execute lifecycle operations that may wait on the current container itself.

For temporary backpressure, usually **do not stop**. Pausing preserves consumer group membership and avoids unnecessary rebalances.

## 10. Distinguishing isPauseRequested from isContainerPaused

Spring Kafka provides APIs to observe pause state at the container level.

| Check | Question answered |
|---|---|
| **isPauseRequested()** | Does the application/container currently have a pause request? |
| **isContainerPaused()** | Has the container reached paused state per container semantics? |
| **ConsumerPausedEvent** | Has an event been published for the consumer's transition to paused? |
| **ConsumerResumedEvent** | Has an event been published for the consumer's transition to resumed? |

Example:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("inventory-listener");

if (container != null) {
    log.info(
            "running={}, pauseRequested={}, containerPaused={}",
            container.isRunning(),
            container.isPauseRequested(),
            container.isContainerPaused());
}
~~~

Do not interpret these states as a strictly atomic snapshot across all callbacks in the system. One thread can call `requestResume` right as another thread reads pause status. Track **desired state** and **observed state** separately if multiple sources issue control commands.

With a concurrent listener container, `isContainerPaused` may only report true once the relevant child consumers have actually paused per parent semantics. An event from **one child** does not prove **the entire parent** is paused.

## 11. ConsumerPausedEvent does not guarantee zero in-flight work

A listener can receive a record and hand business work off to an `ExecutorService`:

~~~java
@KafkaListener(topics = "inventory.commands")
public void onCommand(InventoryCommand command) {
    workerPool.execute(() -> inventoryService.apply(command));
}
~~~

This example requires care because the listener returns before the actual work completes. When the consumer pauses, the worker pool may still have tasks running:

~~~text
12:00:00  Listener receives events A, B, C
12:00:01  A, B, C are enqueued into worker pool
12:00:02  Controller requests pause
12:00:03  ConsumerPausedEvent is published
12:00:04  Workers are still processing B and C
~~~

Thus **ConsumerPausedEvent only indicates the consumer paused**, not that in-flight tasks equal 0.

If a true quiesce point is needed for database maintenance:

1. Request pause to stop submitting new records to the worker pool.
2. Wait for paused state to be observed.
3. Track in-flight work with a dedicated counter/registry.
4. Start maintenance only once in-flight work has drained within a deadline.
5. If tasks cannot complete, use appropriate retry/ack/idempotency mechanisms.

Do not use `ConsumerPausedEvent` to replace counting in-flight tasks or confirming database transactions committed.

## 12. Pause/resume and the Kafka consumer group

A critical difference between pause and stop is that **the consumer remains in the group while paused**. The container continues polling as appropriate to maintain consumer group membership and respond to the broker/coordinator.

~~~text
Before:
  Consumer A -> P0, P1
  Consumer B -> P2, P3

A paused:
  Consumer A still owns P0, P1
  Consumer B still owns P2, P3

A resumed:
  Consumer A resumes processing P0, P1
~~~

Pause/resume normally does not require a rebalance solely because of pause/resume commands. Conversely, stopping a consumer can cause partitions to be redistributed.

However, pause **does not exempt** the consumer from all group membership rules. If the listener processes for too long or the poll thread is blocked, the consumer can still exceed **max.poll.interval.ms**, lose assignments, and trigger a rebalance. A paused event does not guarantee assignments persist forever.

During rolling deployments, pause also does not replace stop/shutdown. If a pod is terminated, the process still must stop per lifecycle rules, and partition ownership is recoordinated by the group.

## 13. Pause after poll or pause after current record?

An important detail is when a pause request takes effect:

~~~text
Consumer.poll() fetched:
  offset 10
  offset 11
  offset 12
  offset 13

Listener is processing offset 10
  |
  +-- another thread calls container.pause()
~~~

Under normal operation, the container may finish processing remaining records from the current poll before pausing. Some Spring Kafka versions support **pauseImmediate** so pausing takes effect after the current record rather than waiting for the entire poll batch to finish.

~~~java
factory.getContainerProperties().setPauseImmediate(true);
~~~

When enabling `pauseImmediate`, the application must understand that the container may retain undelivered records from the previous poll to process after resuming per your version's semantics.

Important: **pauseImmediate does not interrupt a running business listener method mid-flight** and does not discard tasks already submitted to a background executor. It changes where the container stops delivering records, not a cancellation mechanism.

## 14. Per-partition pause vs. whole-container pause

There are two scopes for throttling load:

### Whole-container pause

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("inventory-listener");

if (container != null) {
    container.pause();
}
~~~

Suitable when a shared dependency such as a database connection pool is saturated and all partitions of the listener need to slow down.

### Per-TopicPartition pause

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("inventory-listener");

TopicPartition hotPartition =
        new TopicPartition("inventory.commands", 3);

if (container != null && container.isRunning()) {
    container.pausePartition(hotPartition);
}
~~~

Suitable when only one partition has a specific workload or dependency issue. Corresponding resume:

~~~java
container.resumePartition(hotPartition);
~~~

With per-partition pausing, some Spring Kafka versions provide dedicated partition-level events such as **ConsumerPartitionPausedEvent** and **ConsumerPartitionResumedEvent**. Do not assume a whole-consumer `ConsumerPausedEvent` always fires for every `pausePartition()` call, or use a whole-consumer event to deduce the exact state of all partitions.

Observer design must distinguish **events reflecting consumer-level pause/resume** from **events reflecting partition-level pause/resume** per your running Spring Kafka version's API.

## 15. What is partition info in the event used for?

`ConsumerPausedEvent` and `ConsumerResumedEvent` help identify **the set of TopicPartitions involved in the state transition**. A `TopicPartition` includes:

~~~text
TopicPartition
  topic: inventory.commands
  partition: 3
~~~

Log example:

~~~text
timestamp=12:01:22.500
event=consumer_paused
listener=inventory-listener
partitions=[inventory.commands-0,inventory.commands-1]
reason=database_saturation
~~~

The `listener` and `reason` fields in the log are application-supplied metadata; framework events do not automatically know the **business reason** for pausing. If the reason is backpressure, maintenance, or a circuit breaker, the controller must record that reason where state is managed.

Do not put individual offsets or record IDs into metric labels for pause/resume. Events reflect partition lifecycles, not specific offsets.

## 16. Concurrent listener containers and multiple events

With a `@KafkaListener` configured with concurrency greater than 1, Spring Kafka can create one parent `ConcurrentMessageListenerContainer` and multiple child `KafkaMessageListenerContainer` instances.

~~~text
Parent: inventory-listener
  |
  +-- child 0 -> Consumer A -> P0, P1
  |
  +-- child 1 -> Consumer B -> P2, P3
  |
  +-- child 2 -> Consumer C -> P4, P5
~~~

When calling **pause() on the parent**, pause is coordinated down to the child consumers. Each child has its own poll loop and effective timing. Therefore, `ConsumerPausedEvent` occurrences can appear at different times.

~~~text
12:00:00.000  parent.pause()
12:00:00.080  child 1 paused -> event
12:00:00.150  child 0 paused -> event
12:00:00.310  child 2 paused -> event
~~~

The diagram is illustrative only; there is no guaranteed fixed ordering of child events.

**One child pausing does not mean the entire parent is paused.** When reporting overall listener status, combine events by source/child with parent state APIs like `isContainerPaused()` rather than setting a global flag upon receiving the first event.

During rebalances, partition assignments among children can shift. Never hard-code that P3 always belongs to child 1.

## 17. Do not use event counts as the single source of truth

Suppose a dashboard increments a counter on `ConsumerPausedEvent` and decrements on `ConsumerResumedEvent`:

~~~text
pausedCount += 1 when paused
pausedCount -= 1 when resumed
~~~

This approach can fail in many scenarios:

- Container stops before a resume event occurs.
- Application restarts and loses in-memory event history.
- Rebalances change partition assignments.
- A child container pauses multiple times across different cycles.
- An internal event listener hits an exception or observation misses an event.
- Per-partition pause/resume emits different events from whole-consumer pause/resume.

Therefore:

- Use event counters to measure **state-transition frequency**.
- Use state gauges or poll container APIs to measure **current state**.
- When a service restarts, rebuild state from running containers.
- When a container stops, clear stale state for closed children.

For operational dashboards, maintain **desired paused**, **observed paused**, and **consumer running** rather than a single boolean.

## 18. Designing backpressure with hysteresis

If a system pauses when the worker queue hits 800 and resumes when the queue drops to 799, minor load fluctuations can cause continuous pause/resume flapping.

A better design uses two distinct thresholds:

~~~text
Worker queue capacity: 1000

Queue size >= 800:
    request PAUSE

Queue size <= 300:
    request RESUME

300 < Queue size < 800:
    keep current state
~~~

Example sequence:

~~~text
queue=820 -> pause requested
            |
            v
        ConsumerPausedEvent

queue=690 -> still paused
queue=450 -> still paused
queue=280 -> resume requested
            |
            v
        ConsumerResumedEvent
~~~

Two thresholds create **hysteresis**, reducing state transitions and control oscillation.

The numbers are illustrative only. High/low watermarks must be chosen from throughput, downstream processing speed, memory budgets, and real recovery times.

Consumer lag will rise while paused if producers continue writing to Kafka. That is an intentional trade-off to protect downstream systems; set separate alerts for prolonged pause duration or lag exceeding SLOs.

## 19. Example BackpressureController with event observation

A controller can track requested state from queue depth:

~~~java
@Component
public class InventoryBackpressureController {

    private final InventoryConsumerControl consumerControl;
    private final QueueDepthProbe queueProbe;
    private final AtomicBoolean pauseRequested = new AtomicBoolean();

    public InventoryBackpressureController(
            InventoryConsumerControl consumerControl,
            QueueDepthProbe queueProbe) {
        this.consumerControl = consumerControl;
        this.queueProbe = queueProbe;
    }

    @Scheduled(fixedDelay = 1_000L)
    public void evaluate() {
        int queueDepth = queueProbe.pendingJobs();

        if (queueDepth >= 800
                && pauseRequested.compareAndSet(false, true)) {
            consumerControl.requestPause();
        }
        else if (queueDepth <= 300
                && pauseRequested.compareAndSet(true, false)) {
            consumerControl.requestResume();
        }
    }
}
~~~

`QueueDepthProbe` and `InventoryConsumerControl` are illustrative application components. Enable scheduling and add the appropriate imports/beans.

The `AtomicBoolean` above only tracks **whether the controller requested pause**; it **does not prove the consumer is paused/resumed**. If the container does not exist, stopped, or failed to apply the request, the controller flag can diverge from reality.

In production, you should:

1. Compute desired state from multiple pause sources.
2. Log action requests and failures when containers are unavailable.
3. Observe events and container APIs for observed state.
4. Reconcile state periodically, with bounded request retries if needed.
5. Avoid resuming while another pause reason remains active.

## 20. Multiple simultaneous pause reasons

An application may have multiple sources wanting to pause a consumer:

- Database saturation.
- Open circuit breaker.
- Maintenance window.
- Deep worker queue.
- Manual operator pause.

Suppose:

~~~text
12:00  database overloaded -> PAUSE
12:01  maintenance starts -> stay PAUSED
12:02  database recovers -> DO NOT RESUME
12:10  maintenance ends -> RESUME
~~~

If the database controller calls resume the moment the database recovers, it can accidentally override the active maintenance pause.

A simple model is managing a **set of pause reasons**:

~~~text
pauseReasons = {
  DATABASE_OVERLOAD,
  MAINTENANCE
}

Consumer must pause if set is non-empty.
Consumer resumes only when set is empty.
~~~

`ConsumerPausedEvent`/`ConsumerResumedEvent` tell whether the consumer applied the change, but **are not the policy decision source** and do not store all pause reasons automatically. Control should be centralized in one service/coordinator.

## 21. How should event handlers emit metrics?

An observer can update lightweight metrics:

~~~java
@Component
public class KafkaPauseMetricsObserver {

    private final MeterRegistry registry;

    public KafkaPauseMetricsObserver(MeterRegistry registry) {
        this.registry = registry;
    }

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        registry.counter("kafka_consumer_pause_events_total")
                .increment();
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        registry.counter("kafka_consumer_resume_events_total")
                .increment();
    }
}
~~~

The snippet assumes the application uses Micrometer with a configured `MeterRegistry`. It only counts **how many events were received**, not how many partitions are currently paused.

To know current state, periodically read `isPauseRequested()`/`isContainerPaused()` from the registry and update gauges per listener ID. With a parent concurrent container, if per-child gauges are needed, resolve exact child identities via lifecycle APIs rather than inferring from event counts.

Related metrics:

| Metric | Purpose |
|---|---|
| Pause requests | Count how often controllers request pause |
| `ConsumerPausedEvent` count | Count pause events published by containers |
| Resume requests | Count how often resume is requested |
| `ConsumerResumedEvent` count | Count resume events published by containers |
| Pause request-to-effective latency | Elapsed time between request and corresponding event |
| Current paused state | Actual observed state |
| Pause duration | How long the consumer has remained paused |
| Consumer lag | Accumulating Kafka backlog |
| Listener processing latency | Record and dependency processing load |
| Queue depth | Pressure on worker pools or downstream systems |

Pause duration is more useful than event counts if you need to know how long a consumer has been stuck in the paused state.

## 22. Measuring request-to-effective latency

When `requestPause` is called, the application can record a timestamp. Upon receiving the corresponding `ConsumerPausedEvent`, compute the latency from request until the event is observed.

~~~text
requestPause at 10:00:00.000
ConsumerPausedEvent at 10:00:00.150

Observed transition latency: approximately 150 ms
~~~

However, measurement has risks:

- Concurrent containers emit multiple child events for one parent request.
- A newer request can supersede an older request before its event arrives.
- Assignment changes make the partition set in the event differ from request time.
- Asynchronous event handlers can make callback timestamps lag behind actual pause time.
- If the container was already paused, repeated `requestPause` calls may not emit a new state-transition event.

A reliable tracking implementation needs a **request ID or transition generation** in the controller, per-container/child state, and monotonic clocks appropriate for duration measurement. Do not rely solely on event timestamps to infer strict SLAs without accounting for asynchronous dispatch.

## 23. Pause does not mean consumer.poll() stops

A common misconception: consumer paused means the thread stops polling.

False. With Spring Kafka listener containers, pausing is normally designed to **keep polling** in order to maintain group membership while refraining from delivering new records for paused partitions.

~~~text
Consumer PAUSED
    |
    +-- poll
    +-- heartbeat/group management continues
    +-- poll
    +-- handle rebalance if any
    +-- poll
    +-- wait for resume
~~~

Therefore, CPU/network background activity can still occur during pause, and the consumer still requires broker connectivity.

If the listener is processing an extremely long batch or an event handler blocks the poll thread for too long, the consumer can still hit `max.poll.interval.ms` even though a pause request was sent. Pausing does not cure a blocked thread.

To handle long-running work, evaluate `max.poll.records`, timeouts, proper asynchronous processing/acknowledgment, and partition ownership.

## 24. Pause and offset commits

Pause/resume is a **consumption-rate control** mechanism, not an offset-commit API.

~~~text
P0 records:
  offset 100 -> processed
  offset 101 -> processed
  offset 102 -> in-flight
  offset 103 -> fetched, not yet processed

Pause request
    |
    v
ConsumerPausedEvent

Just because paused does not mean offset 104 is safe to commit.
~~~

If only records 100 and 101 finished, the safe committed offset is typically 102, depending on processing and consumer group policy. If the application manually commits 104 because it paused, records 102/103 can be skipped after a restart.

With Spring Kafka, the container manages commits per **AckMode** and error-handler/transaction settings. With manual acknowledgment, acknowledge only truly successful records. With transactional listeners, offsets can be committed inside the Kafka transaction alongside output records—never commit outside the transaction inside an event handler.

**ConsumerPausedEvent is not an "all offsets committed" signal**. If business logic requires a quiesce barrier before maintenance, additionally verify in-flight completion and commit/transaction outcomes.

## 25. ConsumerResumedEvent and backlog after resume

When dependencies recover, the consumer resumes and may face a large backlog of queued records:

~~~text
Kafka input rate while paused: 200 records/sec
Pause duration: 60 seconds

New backlog: roughly 12,000 records

Resume:
  consumer attempts to catch up on backlog
~~~

The example above assumes a steady input rate and no other consumer group processing those partitions. After resuming, a burst in processing speed can overload the database again, creating a **pause → resume → pause** cycle.

To reduce the risk:

- Use wide enough hysteresis.
- Tune `max.poll.records` and concurrency appropriately.
- Limit concurrent in-flight business tasks.
- Use rate limits or semaphores at dependency boundaries.
- Track backlog age and processing lag, not just queue depth.
- Consider gradual recovery instead of letting the entire system absorb full spike load immediately.

`ConsumerResumedEvent` indicates the system is ready to receive records again; **it does not guarantee processing speed has stabilized**.

## 26. Relationship with retry and backoff

Spring Kafka error handlers can employ backoff or pause/resume strategies on partitions or containers in certain scenarios. Still, distinguish:

1. **Manual container pause**: the application or operator proactively requests pause.
2. **Framework/backoff pause**: the container or error handling throttles per policy.
3. **Partition pause**: only one or a few partitions temporarily pause.
4. **Non-blocking retry topic**: failing records are forwarded via retry topics; retry consumers can wait until due time.

Do not lump every `ConsumerPausedEvent` into a "database overload" conclusion. Business reasons are not necessarily carried by the event; the same observed event can stem from another mechanism in the application.

If multiple systems control pause, establish clear ownership of pause state so a scheduler does not resume while an error handler still needs to hold backoff.

Regarding retries and DLT, **pausing does not alter attempt counts**, exception classifiers, or recovery policies. It only affects when the consumer continues fetching/delivering records.

## 27. Rebalance while the consumer is paused

Pausing does not give partitions absolute immunity from rebalances.

~~~text
Consumer A owns P0, P1
    |
    +-- A pauses P1
    |
    +-- consumer B joins group
    |
    v
Rebalance
    |
    +-- P1 may move to B
    |
    v
Assignment changes
~~~

When assignments change, the listener container must apply pause state appropriate to the partitions it currently owns. Earlier events describe state at **an older point in time** and are not permanent proof of ownership.

With per-partition pause, applications should decide policy when a partition moves consumers:

- Does pause policy apply per **topic-partition** or per **consumer instance**?
- Should a newly assigned partition remain paused for business reasons?
- If the old consumer loses a partition, does the observer clear stale observed paused state?
- Who decides when to resume after a rebalance?

Never store a per-partition paused flag while ignoring revoke/assigned events and actual container state; a stale flag can make dashboards report incorrectly.

## 28. Container stopped differs from container paused

When a container stops, the consumer closes and stops polling. Pause/resume only makes sense while the container is running in its lifecycle.

~~~text
RUNNING
   |
   +-- pause() --> PAUSE_REQUESTED --> PAUSED
   |                                      |
   |                                      +-- resume() --> RUNNING
   |
   +-- stop()  --> STOPPING --> STOPPED
                                      |
                                      +-- start() --> RUNNING
~~~

States in the diagram are an operational model, not the complete enum of states exposed by Spring Kafka.

If a container has stopped, never use `resume()` as a substitute for `start()`. Upon `start()`, a new `KafkaConsumer` joins the group and receives new assignments, after which pause policies must be applied per current configuration.

Do not call stop directly from a `ConsumerPausedEvent` handler when the handler runs on the consumer thread. If you want to stop on a transition, offload to a lifecycle coordinator as noted in the thread-safety section.

## 29. Avoiding event-driven feedback loops

A design bug is letting two observers react oppositely:

~~~text
Observer A:
  sees ConsumerPausedEvent
  -> calls container.resume() immediately

Observer B:
  sees ConsumerResumedEvent
  -> calls container.pause() immediately

Result:
  continuous pause/resume loop
~~~

Events should primarily serve **observation**, while **control policy** should reside in a single controller with clear desired state and reasons.

If reacting to events to issue new commands is genuinely required, enforce:

- Explicit state-transition preconditions.
- Debounce or minimum dwell times.
- Validation of current transition generation.
- Idempotent request handling.
- Rate limits on transitions per minute.
- Alerts when oscillation is detected.

In production, pause/resume loops not only flood logs and metrics, they also cause throughput swings, unpredictable latency, and mask real downstream failures.

## 30. Sample observer storing observed state

An application can maintain a lightweight projection of events for dashboards. With only one listener, you can start simple:

~~~java
@Component
public class PauseStateProjection {

    private final AtomicBoolean observedPaused =
            new AtomicBoolean();

    @EventListener
    public void whenPaused(ConsumerPausedEvent event) {
        observedPaused.set(true);
    }

    @EventListener
    public void whenResumed(ConsumerResumedEvent event) {
        observedPaused.set(false);
    }

    public boolean observedPaused() {
        return observedPaused.get();
    }
}
~~~

**The pattern above illustrates the idea only and is incorrect for multiple consumers if used as-is**. With multiple child containers, one child resuming can set the flag to false even though another child remains paused.

For concurrent containers, maintain a map keyed by child/source identity plus partition set, or compute parent state via container APIs. When containers stop/restart, the projection must clear or refresh state to avoid reporting paused permanently.

If application events dispatch asynchronously, update the projection thread-safely and do not assume callbacks arrive in execution order across threads. Use controller-assigned sequence/timestamps or re-read container state before asserting final state.

## 31. Observing with logs, metrics, and traces

For operations, correlate pause/resume events with the **business reason** held by the controller:

~~~text
event=pause_requested
listener=inventory-listener
cause=database_pool_saturation
queueDepth=850
requestedAt=12:00:00.000

event=consumer_paused
listener=inventory-listener
partitions=[inventory.commands-0,inventory.commands-1]
observedAt=12:00:00.120

event=resume_requested
listener=inventory-listener
cause=database_pool_recovered
queueDepth=260
requestedAt=12:01:30.000

event=consumer_resumed
listener=inventory-listener
partitions=[inventory.commands-0,inventory.commands-1]
observedAt=12:01:30.090
~~~

These are illustrative application structured logs, not default framework output.

A useful dashboard can display:

- Desired vs. observed pause state.
- State-transition latency.
- Pause/resume transitions per hour.
- Consumer lag and oldest record age.
- Queue depth, DB pool utilization, and downstream error rates.
- Paused duration per listener/child consumer.
- Rebalance count and partition assignment changes.
- Listener processing latency before/after resume.

When consumer lag rises, you need to know whether it rose due to an intentional pause, a slow listener, a failing dependency, or a group rebalance; tracking lag alone cannot answer that.

## 32. Operational failure scenarios

### Called pause() yet no ConsumerPausedEvent appears

Check whether the container is running, whether the listener ID is right, whether the poll thread is blocked, whether the pause request took effect, and whether the event listener is registered in `ApplicationContext`.

With concurrent containers, inspect child consumers. If one child is processing a very long record, the parent may not yet reach paused state even if other children already emitted events.

### Called resume() yet container still appears paused

Check whether another pause reason remains active, whether a partition-specific pause is still set, whether another controller requested pause again, and whether the consumer is rebalancing.

Do not use `ConsumerResumedEvent` from one child to conclude the entire parent resumed.

### ConsumerResumedEvent appears yet no new records arrive

The topic may be empty, lag may be 0, partition assignments may have shifted, the consumer group may be at the latest committed offset, or another listener in the same group owns the partitions. Check subscription/assignment and broker connectivity before concluding resume failed.

### Pause observed yet database still receives heavy requests

Business tasks may have been enqueued prior to pause, the listener may be finishing an in-flight batch, or other services may still hit the database. `ConsumerPausedEvent` is not a quiesce barrier for all in-flight work.

### Pause/resume events appear continuously

Check hysteresis, multiple controllers contending over pause state, oscillating queue depth, and event sources. Centralize desired-state coordination in a single place.

### Consumer paused yet still rebalances

Check `max.poll.interval.ms`, blocking listener callbacks, group churn, deployments, and session timeouts. Pausing does not exempt consumers from consumer group lifecycle rules.

### Event metrics report wrong count of paused consumers

Metrics may be counting transitions while being interpreted as current state, or missing handling for child stops/restarts/rebalances. Use container-state gauges and state reconciliation.

## 33. Integration testing: real pause and real resume

Mocking `ConsumerPausedEvent` tests the observer but does not prove `KafkaConsumer` actually pauses. Complete tests should use a test Kafka broker such as **EmbeddedKafka** or **Testcontainers Kafka**.

### Test 1: whole-container pause

1. Create topic `inventory.commands` with multiple partitions.
2. Start the listener and wait for assignment.
3. Call `container.pause()`.
4. Await `ConsumerPausedEvent` from the listener observer.
5. Verify `isPauseRequested()` and `isContainerPaused()` per container semantics.
6. Send additional records and verify the listener delivers no new records once pause is in effect.
7. Verify the consumer did not stop/restart simply because of pause.

### Test 2: resume

1. Start from an already-paused container.
2. Call `container.resume()`.
3. Await `ConsumerResumedEvent`.
4. Verify the paused state has ended.
5. Verify records remaining in Kafka continue being delivered to the listener.
6. Verify offset commits and successful processing per `AckMode`.

### Test 3: pauseImmediate

1. Configure batch polling with multiple records.
2. Let the listener receive one record, then call `requestPause` from another thread.
3. Run the test with `pauseImmediate` configured.
4. Verify record delivery stops after the expected boundary.
5. Resume and verify remaining unprocessed records continue delivering without data loss.

### Test 4: concurrent container

1. Create a listener with concurrency > 1 and a multi-partition topic.
2. Request pause on the parent.
3. Collect events from child consumers.
4. Verify the whole parent is not concluded paused before parent status reflects it.
5. Resume the parent and verify children continue receiving records.

### Test 5: partition-specific pause

1. Assign at least two partitions to the consumer/container.
2. Pause one `TopicPartition`.
3. Verify that partition delivers no new records after pause takes effect.
4. Verify the other partition continues processing.
5. Resume that partition and verify records continue.
6. If your version supports partition pause/resume events, verify the exact event types.

### Test 6: controller hysteresis

1. Drive a fake `QueueDepthProbe` up to the high watermark.
2. Verify the controller emits one pause request.
3. Lower queue depth while staying above the low watermark; do not resume.
4. Drop past the low watermark; emit one resume request.
5. Verify no abnormal pause/resume oscillation occurs.

### Test 7: in-flight processing

1. Have the listener enqueue a long-running task.
2. Request pause and wait for `ConsumerPausedEvent`.
3. Verify the task can still be running.
4. Wait for the task to complete or handle per timeout policy.
5. Verify acknowledgments/offsets do not advance past incomplete records.

### Test 8: rebalance while paused

1. Pause the container.
2. Add or stop another consumer in the same group.
3. Observe rebalance and new partition assignments.
4. Verify pause policies apply accurately to current ownership.
5. Verify observed state does not keep revoked partitions marked as current state.

Use condition-based waits with timeouts instead of fixed sleeps that assume events already fired. Results must be verified against container state, callback observations, and actual delivered records.

## 34. Common misconceptions

**Calling container.pause() means the consumer is paused immediately.** False. It is a request; the consumer thread applies it at an appropriate point and emits an event once active.

**ConsumerPausedEvent means the consumer stopped polling.** False. The container normally keeps polling to preserve group membership.

**ConsumerPausedEvent means all business tasks finished.** False. In-flight tasks or already-polled records may still be processing.

**ConsumerResumedEvent proves the next business event succeeded.** False. It only marks that the consumer resumed.

**Pausing always causes a rebalance.** False. Pausing normally preserves partition ownership; stopping can trigger rebalances.

**@EventListener always runs on a separate thread.** False. Event listeners can run synchronously on the consumer thread; never block for long.

**You can call KafkaConsumer.pause() from any thread.** False. `KafkaConsumer` is not thread-safe for arbitrary access; prefer Spring listener container APIs.

**One child ConsumerPausedEvent means the entire concurrent container is paused.** False. Children have independent poll/lifecycles; inspect the parent or all children.

**ConsumerPausedEvent automatically tells why it paused.** Not necessarily. Business reasons must be stored by the controller and attached to logs/metrics.

**A counter of paused events equals the number of currently paused consumers.** False. Counters measure transitions, not current state.

**Pause taking effect means all offsets committed.** False. Pausing is not an offset commit or transaction completion barrier.

**Resume can be used to start a stopped container.** False. Stopped containers require `start()` per lifecycle.

**Increasing max.poll.interval.ms is enough to solve all backpressure.** False. You must control work intake rate, processing duration, queues, threads, and downstream capacity.

**A single boolean paused flag suffices for all listeners.** Insufficient when multiple containers, multiple child consumers, and multiple pause reasons exist.

## 35. Production implementation guide

When an application needs `ConsumerPausedEvent` and `ConsumerResumedEvent` for reliability operations:

1. Define the pause objective: load shedding, waiting for dependencies, maintenance, or per-partition throttling.
2. Use **container.pause()/resume()** instead of calling `KafkaConsumer` directly from worker threads.
3. Distinguish **desired pause state**, **pause requested**, and **pause actually in effect**.
4. Register `@EventListener` for `ConsumerPausedEvent`/`ConsumerResumedEvent` and keep callbacks short.
5. Never call `container.stop()` synchronously from an event callback that may run on the consumer thread.
6. With concurrent containers, track source/child identities and parent status rather than a global boolean.
7. If per-partition pausing is needed, use `pausePartition`/`resumePartition` and partition-specific events as supported by your version.
8. Use high/low watermarks, hysteresis, and a single coordinator unifying pause reasons.
9. Never treat pause events as proof that in-flight business tasks drained or offsets committed.
10. Use `AckMode`, error handlers, transactions, and idempotency suited to your processing model.
11. Monitor queue depth, consumer lag, pause duration, transition latency, and processing throughput.
12. Handle rebalance/assignment changes and prevent stale pause state after consumer restarts.
13. Design recovery on resume so throughput does not spike excessively.
14. Test real broker pause/resume, concurrency, `pauseImmediate`, partition pause, and in-flight processing.

**ConsumerPausedEvent** and **ConsumerResumedEvent** provide critical observation points between control commands and actual consumer state. Properly paired with pause/resume APIs, they confirm when backpressure has taken effect, measure pause durations, and detect state drift between controllers and containers. Still, they only reflect **consumer lifecycle**, not offset handling, business task completion, or transaction boundaries. A resilient design pairs intentional load control with event observation while preserving safe reprocessing when consumers resume or rebalance.
