# Resume Listener Container

In Spring Kafka, when downstream is overloaded, the database hits its connection limit, a worker queue is nearly full, or a dependent component needs maintenance, an application can **pause the listener container** to temporarily stop accepting more records into the business processing pipeline. However, pausing is only half of the backpressure flow: once the system has recovered, the application must **resume the listener container** at the right time to continue consuming from Kafka without losing records or creating a sudden load spike.

The primary API is `MessageListenerContainer.resume()`. This method asks Spring Kafka to **cancel the container-managed pause state** and allow the consumer to resume fetching records from allowed partitions. Depending on lifecycle and polling timing, resume may not take effect at the exact line of the call: the container applies the change on the consumer thread during an appropriate poll cycle.

Resume is **not the same as** `start()`, is not equivalent to `seek()`, and does not commit offsets on its own. It controls record consumption after a pause period while keeping the consumer in the group as long as the container is running and polling periodically.

## 1. Context: what problem do pause and resume solve?

A Kafka consumer often processes faster or slower than downstream at different times. If inbound traffic increases while downstream can only process a fraction of it, continuing to accept records nonstop can cause:

- In-application queues to swell, consuming excessive heap.
- Thread pools to saturate and trigger rejections.
- Databases to run out of connections or hold long transactions.
- Downstream HTTP services to throttle or time out.
- Consumers to fail to process polls in time and increase rebalance risk.
- Retry storms when many records fail together due to a degraded dependency.

Proactive backpressure lets you reduce the amount of new work entering the application:

~~~text
Kafka topic
    |
    v
Spring Kafka listener container
    |
    +---- RUNNING state, not paused
    |         |
    |         v
    |      @KafkaListener
    |         |
    |         v
    |    Database / HTTP / worker queue
    |
    +---- When downstream is overloaded
    |         |
    |         v
    |       pause()
    |         |
    |   Container continues polling to stay in group
    |   but stops delivering new records to listener
    |
    +---- When downstream is healthy enough
              |
              v
           resume()
              |
              v
        Resume delivery and processing
~~~

Pause/resume is a **consumption rate-control** mechanism, not a tool to fix corrupted data. If a record always throws an exception due to a malformed payload, resuming will not make the record valid; you need an error handler, DLT, or recovery procedure.

## 2. Key APIs

Spring Kafka provides pause/resume capabilities through listener containers such as `KafkaMessageListenerContainer` and `ConcurrentMessageListenerContainer`. With `@KafkaListener`, applications typically obtain the container from `KafkaListenerEndpointRegistry`.

| API | Meaning | Notes |
|---|---|---|
| `container.pause()` | Requests pausing record consumption for the container | May not take effect immediately on the consumer thread |
| `container.resume()` | Requests canceling pause to resume consumption | Applied according to the poll/lifecycle cycle |
| `container.isPauseRequested()` | Whether an application/container pause has been requested | Reflects intent, not proof that every partition is paused |
| `container.isConsumerPaused()` | Whether the consumer is actually in the container-managed paused state | With a concurrent container, understand child consumers' states |
| `container.isRunning()` | Whether the container is running | Resume does not replace starting a stopped container |
| `container.pausePartition(tp)` | Requests pausing a specific partition | Applies only in versions supporting partition-level pause |
| `container.resumePartition(tp)` | Allows a paused partition to resume | Does not imply resuming all partitions |

Partition-level methods and partition-level status queries depend on the Spring Kafka version; check the corresponding API in your project dependencies.

### 2.1. Pause requested vs. consumer paused

Suppose an operator thread calls `container.pause()` just as the listener has received a batch of records:

~~~text
Time T0: container.pause()
         isPauseRequested() = true

Time T1: listener is still processing records from previous poll

Time T2: consumer thread reaches the pause application point
         isConsumerPaused() = true

Time T3: operator calls container.resume()
         isPauseRequested() = false

Time T4: consumer thread applies resume
         isConsumerPaused() = false
~~~

This is an illustrative sequence, not a guarantee of exact timing. Do not conclude that `resume()` failed merely because `isConsumerPaused()` is still true on the very next line. Wait for an appropriate poll cycle or listen for resume events.

### 2.2. Resume does not commit offsets

The consumer group's committed offset determines the recoverable reading position. `resume()` only allows the consumer to resume polling/delivering records; it is not a `commitSync()` or `acknowledge()` operation.

If offsets were committed before pausing, after resuming the consumer continues from the appropriate position according to consumer state. If unprocessed records remain from the previous poll, the container may continue processing them before receiving new records, depending on pause and listener configuration.

## 3. Obtaining the listener container via KafkaListenerEndpointRegistry

For applications using `@KafkaListener`, the common approach is to set a stable `id` on the listener and look up the container via the registry.

Listener example:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "order-processing")
    public void onOrder(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
~~~

Retrieving the container and resuming:

~~~java
@Service
public class OrderListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrderListenerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean resumeOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null || !container.isRunning()) {
            return false;
        }

        container.resume();
        return true;
    }
}
~~~

In this example, `true` only means **a resume request was sent to a running container**; it does not prove the consumer has actually resumed or that a new record has been processed. If confirmation is needed, monitor `isConsumerPaused()` and lifecycle events.

### 3.1. Why is id needed?

The registry needs an identifier to find the right listener. With multiple `@KafkaListener` methods, Java method names may collide across beans or not reflect the actual container ID. Setting an explicit `id` helps operations avoid resuming the wrong consumer.

Declare a separate `groupId` to make the consumer group explicit. In Spring Kafka, listener ID and group ID can influence each other depending on annotation semantics and version; specifying both explicitly avoids unintended group ID changes.

### 3.2. Registry cannot find the container

`getListenerContainer("ordersListener")` can return null if:

- The ID does not match a registered container name.
- `@KafkaListener` was not scanned or the bean was not created.
- The container was created directly rather than via the corresponding registry.
- The operator is calling a different application instance.
- Application configuration conditionally enables the listener by profile.

Do not automatically call `start()` for an arbitrary ID just because the registry returned null. Verify that the listener is registered and in the proper lifecycle.

## 4. Resume differs from start, stop, and restart

This is a frequent source of errors in runbooks.

| Action | Does consumer stay in group? | Purpose |
|---|---|---|
| `pause()` | Usually yes, because the container keeps polling | Temporarily halt delivery, avoid additional load |
| `resume()` | Resumes consumption in a running container | End the pause |
| `stop()` | Consumer stops; group may rebalance | End container lifecycle |
| `start()` | Creates/starts consumer per lifecycle | Start a stopped or unstarted container |
| `seek()` | Changes partition reading position | Controlled replay or position adjustment |

If the container is `stop()`ped, calling `resume()` is not the right way to restart it. Call `start()` according to the proper lifecycle and operational conditions.

If the container is running but paused, `start()` is not the symmetrical counterpart to `pause()`. Use `resume()`; do not proactively stop/start just to recreate the consumer when unnecessary.

### 4.1. Why does pause keep the consumer group stable?

When the container pauses, Spring Kafka continues calling `poll()` under its management so the consumer maintains group interaction and heartbeats. This helps avoid rebalances triggered merely by temporarily halting record delivery.

However, pause does not guarantee immunity from all rebalances. A consumer can still lose group membership due to:

- Container stop or process crash.
- Network/broker instability.
- A listener processing a single record for too long before returning to poll.
- Failing to meet `max.poll.interval.ms` under specific conditions.
- Group changes caused by scale-out or rolling deployments.

In other words, pause helps control the inflow of new work, but it cannot rescue a listener that blocks indefinitely before the container has a chance to poll.

## 5. When does resume take effect?

Spring Kafka discourages applications from calling `KafkaConsumer.resume(...)` directly from an arbitrary management thread. KafkaConsumer is not thread-safe for arbitrary operations; the container owns the consumer and knows the safe time to pause/resume.

When the application calls `container.resume()`:

1. The container-managed pause request is cleared.
2. The consumer thread applies the change to partitions permitted to resume during an appropriate poll cycle.
3. The container can fetch/deliver subsequent records.
4. A resume event may be published when the actual state changes.

Avoid writing a busy-wait loop on a request thread:

~~~java
container.resume();
while (container.isConsumerPaused()) {
    // Wrong: spins CPU continuously with no timeout.
}
~~~

Instead, an admin response can return `202 Accepted` meaning "requested," and then use state/events or a health check to track the state transition.

### 5.1. Poll timeout affects control latency

Containers typically apply pause/resume around poll boundaries. Therefore, state-transition latency can depend on poll timeout, processing of current records, and consumer thread scheduling. Do not set an SLO that "resume must finish instantaneously" without measuring actual behavior.

### 5.2. Do not confuse polling with delivery

In the paused state, the container still polls to maintain the consumer group but does not deliver new records to the listener from paused partitions under normal operation. After resume, polling can return records and the listener then resumes processing.

If the topic has no new records or lag is 0, the consumer has resumed successfully even though the listener may not immediately receive new messages. Do not treat "no listener logs" as proof that resume failed.

## 6. pauseImmediate and records fetched from the prior poll

By default, a listener container's pause request is usually applied after the container finishes processing records from the current poll. Therefore, right after `pause()`, the listener may still receive a few more records **that were already polled earlier**.

Spring Kafka provides `ContainerProperties.pauseImmediate` in supporting versions. When enabled, the container can pause after processing the current record instead of waiting for all records from the prior poll to finish; remaining records are retained in memory to continue delivery after resume.

Configuration example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties()
            .setPauseImmediate(true);
    factory.setConcurrency(3);

    return factory;
}
~~~

In the listener:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "order-processing",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void onOrder(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

### 6.1. Illustrative progression

Suppose a poll returns five records: offsets 100, 101, 102, 103, 104.

**Without pauseImmediate:**

~~~text
Poll: [100, 101, 102, 103, 104]
Process 100
pause() requested
Process 101, 102, 103, 104
Container applies pause before subsequent poll
~~~

**With pauseImmediate:**

~~~text
Poll: [100, 101, 102, 103, 104]
Process 100
pause() requested
Container pauses after current record
Retains [101, 102, 103, 104] in memory
resume() requested later
Container delivers retained records
~~~

This is a conceptual diagram for a record listener; the actual record count and how the container delivers batches depend on the version and listener type.

### 6.2. Resume does not mean an entirely fresh poll

When `pauseImmediate` holds records in memory, after resume the container can deliver **records already polled but not yet processed** before advancing to a new batch. This is not a duplicate merely because observed offsets did not advance compared to when pause happened; those records simply had not been processed by the listener yet.

If the application crashes while paused, uncommitted records may be redelivered after restart. Therefore, side-effect design must still tolerate at-least-once/redelivery semantics.

## 7. Resuming when concurrency is greater than 1

With `ConcurrentMessageListenerContainer`, a single listener bean can run multiple child consumers according to `concurrency`. Each child consumer typically handles a set of partitions assigned by the broker.

~~~text
@KafkaListener(id="ordersListener")
                |
                v
ConcurrentMessageListenerContainer
       |           |           |
       v           v           v
   consumer-0   consumer-1   consumer-2
   partitions   partitions   partitions
     [0,3]        [1,4]        [2,5]
~~~

When calling `pause()` or `resume()` on the **parent concurrent container**, Spring Kafka manages the request across the child consumers per container design. You do not need to manually grab KafkaConsumer instances from individual listener threads to resume them.

### 7.1. Meaning of isConsumerPaused

In a concurrent container, the aggregate state `isConsumerPaused()` must be understood in the context of multiple child consumers: some children may have already applied pause/resume while others are still finishing their current record or poll.

Therefore:

- `isPauseRequested()` indicates the container-level request.
- `isConsumerPaused()` reflects the actual state per the container implementation.
- Consumer/partition events help verify state transitions.
- Do not assume all child threads switch in the exact same millisecond.

### 7.2. Multi-instance

Each process/pod has its own `KafkaListenerEndpointRegistry`. If the system runs four pods in the same group, calling `resume()` in pod A **does not** command the consumers on pods B, C, and D.

An admin API hitting one instance controls only that consumer instance, unless the application explicitly builds distributed coordination. For deployment-wide pause/resume commands:

1. Have a control plane or shared configuration defining the policy.
2. Each pod reconciles the desired state with its local container.
3. The system records which pods have applied the request.
4. Operators declare the whole deployment resumed only when target instances have confirmed.

Do not confuse local container operations with cluster-wide broker or consumer group operations.

## 8. Resuming only a single partition

Sometimes one partition has a large volume of records or problematic data while other partitions process fine. Spring Kafka has partition-level pause/resume APIs in supporting versions:

~~~java
TopicPartition partition =
        new TopicPartition("orders.events", 2);

MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null && container.isRunning()) {
    container.resumePartition(partition);
}
~~~

The `resumePartition` API only cancels the pause request for that partition; it does not necessarily cancel a container-wide pause state if the container is still paused at the container level or for another managed reason.

### 8.1. When to use partition-level control?

- Only one partition needs throttling.
- A tenant/business key is concentrated on one partition and needs temporary isolation.
- You want partial recovery instead of unleashing the entire backlog at once.
- A partition is permitted to resume after its data stream has been fixed.

However, partition-level pause does not replace retry/error handling for poison pills. If a record is malformed, resuming the partition may immediately reproduce the failure. Fix the root cause first.

### 8.2. Ownership and rebalance

Partition assignments can change due to rebalances. A partition belonging to child consumer A may move to consumer B. Before controlling a partition, verify the container manages the appropriate assignment and the API applies the request for that partition in the running version.

Do not use consumer group lag alone to infer which process owns a partition; assignments must be read from actual group/container state.

## 9. ConsumerPausedEvent and ConsumerResumedEvent

Spring Kafka emits pause/resume application events such as `ConsumerPausedEvent` and `ConsumerResumedEvent`. They are useful because they reflect **actual state transitions** rather than just API calls issuing a request.

Example:

~~~java
@Component
public class KafkaPauseResumeEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPauseResumeEvents.class);

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info("Kafka consumer paused: partitions={}",
                event.getPartitions());
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info("Kafka consumer resumed: partitions={}",
                event.getPartitions());
    }
}
~~~

This example uses event APIs present in Spring Kafka; exact package/field details depend on the version. For monitoring, include listener/container ID, service instance, and timestamp to distinguish multiple consumers.

### 9.1. Do not perform heavy I/O inside event callbacks

Application events may be published synchronously depending on `ApplicationEventMulticaster` configuration. If a callback executes a long HTTP request or blocks, it can impede the container's processing flow.

Prefer:

- Writing concise logs.
- Updating local atomic state or counters.
- Emitting metrics through lightweight instrumentation.
- If calling an external management system is necessary, offloading the event to a bounded async pipeline with its own error handling.

Do not repeatedly call `resume()` right inside `ConsumerPausedEvent` just because you see the consumer paused, as that can create state-flipping loops and defeat backpressure.

## 10. When is resuming permitted?

A good resume decision does not rely solely on "30 seconds have passed." Verify that the resource that triggered the pause truly has capacity to accept more work.

Useful signals:

| Signal | When can you resume? | Risk if checked poorly |
|---|---|---|
| Worker queue depth | Queue drops below low-watermark | Queue can immediately fill up again |
| Database connection utilization | Free connection count stabilizes | Resume triggers a connection storm |
| HTTP downstream error rate | Errors/timeouts return to acceptable levels | Retry storm immediately after resume |
| Circuit breaker | Transitions to half-open trial or closed per policy | Half-open gets overloaded |
| Recovery/DDL migration | Maintenance step is complete | Consumer runs against an unready schema |
| Disk/memory pressure | Memory drops and is no longer near OOM threshold | In-memory queue keeps growing |
| Manual maintenance flag | Operator intentionally clears pause command | Automation resumes against operator directive |

Do not resume based solely on **when it was paused**. If the root cause has not been resolved, resuming usually just triggers a new wave of failures.

### 10.1. High watermark and low watermark

To prevent the container from pausing/resuming continuously when queue depth fluctuates around a single threshold, use hysteresis:

~~~text
queue capacity = 1,000

>= 800 tasks pending: pause
<= 200 tasks pending: resume

201..799: keep current state
~~~

Example:

~~~text
Pending: 100 -> 500 -> 850 : PAUSE
Pending: 850 -> 650 -> 250 : still PAUSED
Pending: 250 -> 190        : RESUME
Pending: 190 -> 420        : still RUNNING
~~~

The gap between the two thresholds reduces flapping. Choose thresholds based on processing rate, queue capacity, memory, and downstream latency rather than copying illustrative values into production.

## 11. Example BackpressureCoordinator that auto-resumes on recovery

A coordinator can periodically observe queue depth and downstream status, then reconcile the listener container according to policy.

~~~java
@Component
public class OrdersBackpressureCoordinator {

    private static final int HIGH_WATERMARK = 800;
    private static final int LOW_WATERMARK = 200;

    private final KafkaListenerEndpointRegistry registry;
    private final WorkQueueMeter queueMeter;
    private final DownstreamHealth downstreamHealth;

    public OrdersBackpressureCoordinator(
            KafkaListenerEndpointRegistry registry,
            WorkQueueMeter queueMeter,
            DownstreamHealth downstreamHealth) {
        this.registry = registry;
        this.queueMeter = queueMeter;
        this.downstreamHealth = downstreamHealth;
    }

    @Scheduled(fixedDelay = 1_000)
    public void reconcile() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null || !container.isRunning()) {
            return;
        }

        int pending = queueMeter.pending();
        boolean healthy = downstreamHealth.isReady();

        if (!healthy || pending >= HIGH_WATERMARK) {
            if (!container.isPauseRequested()) {
                container.pause();
            }
            return;
        }

        if (pending <= LOW_WATERMARK
                && container.isPauseRequested()) {
            container.resume();
        }
    }
}
~~~

`WorkQueueMeter` and `DownstreamHealth` are illustrative business abstractions, not built-in Spring Kafka classes. Enable scheduling via `@EnableScheduling` (or equivalent configuration) if using `@Scheduled`.

This coordinator illustrates automatic pause/resume by queue and dependency health. In real systems, handle **multiple pause reasons** and **manual overrides** so you do not automatically resume a listener that an operator intentionally kept paused.

### 11.1. Multiple pause reasons: do not let one source resume prematurely

Suppose there are three reasons:

- `QUEUE_FULL`.
- `DOWNSTREAM_UNHEALTHY`.
- `MANUAL_MAINTENANCE`.

If the queue shrinks and the scheduler calls `resume()` while an operator is still performing database maintenance, the listener will take load too early. The container API is not a full "pause reason" management system; the application should store desired state separately.

A good model:

~~~text
Desired state = PAUSED
if any pause reason is active

Desired state = RUNNING
only if all pause reasons are cleared

Reconciler:
  desired PAUSED  -> container.pause()
  desired RUNNING -> container.resume()
~~~

You can maintain a synchronized set of pause reasons in the application control plane and log state transitions. Avoid letting the health checker, operator API, and queue monitor call `resume()` independently without knowing about each other.

## 12. Manual resume via an admin API

Sometimes operations wants to manually resume after maintenance. An admin service can provide a resume-request operation:

~~~java
@RestController
@RequestMapping("/internal/kafka/listeners")
public class KafkaListenerAdminController {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerAdminController(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @PostMapping("/orders/resume")
    public ResponseEntity<String> resumeOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null) {
            return ResponseEntity.notFound().build();
        }
        if (!container.isRunning()) {
            return ResponseEntity.status(409)
                    .body("Container stopped; start is required");
        }

        container.resume();
        return ResponseEntity.accepted()
                .body("Resume requested");
    }
}
~~~

The example above is a skeleton without authentication or a state coordinator. In production, the endpoint must:

- Require operator-level authentication and authorization.
- Never be exposed directly to the public internet.
- Audit who issued the command, when, and for what reason.
- Verify downstream is genuinely ready.
- Interact with the central pause-reason state rather than bypassing policy.
- Return a "requested" semantic rather than claiming it has already applied across all consumers.

If a listener is paused for intentional maintenance, the resume API should clear the maintenance reason and let the coordinator reconcile; do not call `resume()` directly against the desired state.

### 12.1. Manual resume in a multi-pod system

An HTTP request usually reaches only one pod via a load balancer. Thus, a `202 Accepted` response from one pod does not prove all pods have resumed.

To control the entire group, use a management job sending requests to each instance or a shared config/coordination store observed by every instance. Confirm per-instance status before completing the action on a dashboard.

## 13. What pause/resume does not handle for you

### 13.1. In-flight records still need to finish safely

Pausing blocks fetching/delivering additional records, not automatic rollback or cancellation of all ongoing work. A record currently being processed by the listener may still keep running when pause is requested.

If the listener calls the database and commits before pausing, offset commit is still handled by the container per ack mode and transaction policy. If the listener fails, the error handler/retry must handle the error independently.

### 13.2. Async queues are not automatically safe

A dangerous pattern:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
    // Listener returns before the task completes.
}
~~~

If the container treats the listener as successful and commits the offset before the worker finishes, a process crash can lose the business side effect. Pause/resume cannot fix this bug.

With asynchronous processing, you need:

- Ack/commit only after durable side effects or successful recovery.
- Bounded worker queue capacity.
- Error propagation and retry/DLT for worker failures.
- Concurrency and acknowledgment semantics matching the Spring Kafka version.
- Backpressure mechanisms preventing the queue from accepting more work when nearly full.

### 13.3. Resume does not eliminate duplicate delivery

An at-least-once consumer can reprocess records after a crash before commit. When resuming after a pause, uncommitted records can also be redelivered per lifecycle. Business handlers need idempotency via event IDs, an inbox, unique constraints, or an equivalent mechanism.

### 13.4. Resume does not alter seek positions

If an operator adjusted group offsets or the container sought to another position, `resume()` does not reverse the seek operation. Do not use resume as a way to "go back to the offset before pause"; it does not store a separate checkpoint independent of Kafka offsets.

## 14. When the framework pauses the consumer itself

Not every pause originates from an operator's pause button. Spring Kafka can also temporarily pause a consumer due to error handling, backoff, or special acknowledgment modes.

For example, with `asyncAcks`, the container may pause delivery while acknowledgments from a prior poll remain incomplete. Only once outstanding acks are adequately resolved can the container safely proceed under that mode's semantics.

### 14.1. Calling resume cannot bypass all internal mechanisms

If the framework still has a reason to keep the consumer paused, an application's `resume()` request may not immediately make the listener receive records. Before forcing action:

1. Identify who requested the pause.
2. Check manual/app-level pause requests.
3. Check active error handlers/backoffs.
4. Check outstanding manual acknowledgments, especially when using `asyncAcks`.
5. Check individual partition pauses.
6. Verify the container is still running and the consumer has assignments.

Do not try to "fix" a waiting consumer by calling `resume()` repeatedly in a loop. If acks are missing or an error handler has not completed, resolve the waiting condition.

### 14.2. Partition paused vs. container paused

If the application calls container-wide `resume()` while partition-level pause requests remain active, those partitions may stay paused. Conversely, calling `resumePartition(tp)` does not automatically clear a container-level pause request.

When investigating, check both state levels and the APIs available in your deployed Spring Kafka version.

## 15. Consumer lag after resuming

During a pause, producers may continue writing new data to the topic. Because the consumer group is not processing new records, lag typically rises. After resuming, the consumer must process the backlog:

~~~text
Time --------->
Input rate:   100 100 100 100 100 100
Consume rate: 100   0   0   0 150 150
State:        RUN PAUSE PAUSE RUN RUN RUN
Lag:            0 100 200 300 250 200 ...
~~~

Numbers are illustrative only. If post-resume processing capacity only equals the ongoing producer write rate, the backlog will **not shrink**. To catch up, net processing capacity must exceed the inbound rate, or the system needs sufficient time/scaling.

### 15.1. Resuming can create a burst

If multiple consumers resume simultaneously after a downstream outage, all of them may begin draining the backlog and overload downstream again.

Mitigations:

- Resume per instance or per partition when needed.
- Constrain concurrency/worker queues appropriately.
- Use rate limiters or adaptive backpressure at the application layer.
- Keep high/low watermarks to pause again when genuinely necessary.
- Monitor database pools, downstream latency, and error rates during backlog catch-up.

Do not assume pause/resume limits record rate on its own. It is an on/off delivery switch, not a token-bucket rate limiter.

### 15.2. High lag upon resume is not necessarily an incident

High lag right after resuming is usually the expected consequence of a pause interval. What to watch is:

- Is lag **steadily decreasing**?
- Is the oldest record age dropping back below SLA?
- Have error/retry rates returned to low levels?
- Is downstream latency stable?
- Is a pause/resume oscillation loop occurring?

A dashboard showing only point-in-time lag can be misleading. Track both lag trends and processing rates.

## 16. Metrics and logs for pause/resume

| Metric or state | Meaning |
|---|---|
| Pause requested | Whether the application has requested a pause |
| Consumer paused | Actual pause state of the container/consumer |
| Pause duration | How long a pause period has lasted |
| Resume request count | Number of resume requests issued |
| Resume applied/event count | Number of resumes actually applied |
| Consumer lag per partition | Whether backlog is growing or shrinking |
| Record processing rate | Processing capacity after resume |
| Oldest unprocessed record age | Latency relative to SLA |
| Worker queue depth | In-application pressure |
| Downstream error/latency | Whether the dependency has actually recovered |
| Rebalance count | Whether the group became unstable during pause/restore |

Not all of these metrics are automatically available under exact table names. You can use Micrometer, Kafka client metrics, application events, and custom instrumentation.

### 16.1. Structured logging

Example state-transition log:

~~~text
event=kafka_listener_resume_requested
service=orders-worker
instance=pod-a
listenerId=ordersListener
groupId=order-processing
reasonCleared=QUEUE_FULL
queueDepth=170
downstreamHealthy=true
requestedPause=false
~~~

And once the application event arrives:

~~~text
event=kafka_consumer_resumed
instance=pod-a
listenerId=ordersListener
partitions=orders.events-0,orders.events-2
~~~

These are log format examples, not fields emitted by Spring Kafka by default. Do not log payloads, credentials, or sensitive Kafka record keys solely to diagnose resume.

### 16.2. Useful alerts

- Container remains paused beyond allowed duration while downstream is healthy.
- Resume requested but resume applied is not observed after a reasonable wait.
- Queue depth remains high despite the consumer being paused for a long time.
- Lag continues growing unboundedly after resume.
- Too many pause/resume flappings within a few minutes.
- One instance fails to resume while other instances are already running.
- Consumer container is not running while operators think it is merely paused.

Combine pause reason, poll state, and downstream health for actionable alerts. Do not page simply because a consumer is paused during planned maintenance.

## 17. Runbook: resume was called but the listener stays silent

1. Look up the right listener ID from `KafkaListenerEndpointRegistry`.
2. Confirm `container != null` and `container.isRunning() == true`.
3. Check whether `isPauseRequested()` is still true.
4. Check `isConsumerPaused()` and `ConsumerResumedEvent`.
5. Check whether any partition-level pause requests remain uncleared.
6. Check whether the framework is holding the pause due to `asyncAcks`/error handler.
7. Check consumer group assignments and partition ownership.
8. Check whether the topic has new records or consumer lag is still greater than 0.
9. Check whether the listener is blocked processing a record from the previous poll.
10. Inspect logs/errors/rebalances for other causes.

If the container has resumed but the topic has no new records, a silent listener is normal. If the container is stopped, use lifecycle start per procedure instead of spamming resume.

## 18. Runbook: consumer immediately pauses again after resume

1. Inspect the coordinator's pause reason state.
2. Check whether queue depth still exceeds `HIGH_WATERMARK`.
3. Check whether downstream error rate/circuit breaker still evaluates as unhealthy.
4. Check whether an operator/manual maintenance flag is still active.
5. Determine whether multiple schedulers/controllers are calling pause/resume simultaneously.
6. Inspect metric timestamps to see which component triggered the new pause.
7. If the queue cannot drain, adjust worker throughput or the dependency rather than merely increasing resume attempts.

This is often a sign that the policy is properly preventing overload, or that two controllers are fighting for control. Avoid blindly tuning thresholds just to flip the pause metric to false.

## 19. Runbook: duplicate records appear after resume

1. Determine whether duplicates are the same topic/partition/offset redelivered or two distinct events with identical payloads.
2. Check committed offsets before pause and after resume.
3. Check for crashes/rebalances during the pause period.
4. Check whether the listener persisted side effects before committing offsets.
5. Check whether manual ack and async workers completed durably before acknowledging.
6. Check whether the error handler sought back to unprocessed records.
7. Verify idempotency keys and database uniqueness constraints.

Resume does not create end-to-end exactly-once semantics by itself. Duplicate delivery can be a valid outcome of at-least-once semantics. You need business deduplication and proper ack/commit practices.

## 20. Runbook: resume overloads downstream again

1. Observe the resume timestamp of each instance.
2. Determine total concurrency and how much processing rate jumped.
3. Inspect queue depth, DB connections, HTTP 429/503, and p95 latency.
4. Choose staggered resume or partition-level resume where appropriate.
5. Keep bounded queues and high/low watermarks.
6. Consider a separate rate limiter or circuit breaker.
7. Watch lag decrease while downstream stays within safe thresholds.
8. If the dependency lacks capacity, address the capacity limit or adjust SLOs/scaling.

Do not count "lag dropped quickly after resume" as a success if the database simultaneously overloaded and error rates spiked.

## 21. Runbook: container is stopped, not paused

1. Check `container.isRunning()`.
2. Confirm whether stop was caused by an operator, shutdown, fatal error, or `autoStartup` false.
3. Inspect bean lifecycle and consumer group membership.
4. Check whether a shutdown is in progress to avoid starting mid-stop.
5. After identifying the cause and ensuring the dependency is ready, use `start()` following a valid lifecycle.
6. Verify partition assignment and consumption after start.
7. If it must start in a paused state immediately, manage desired state so an unintended burst of load is not created.

Do not use `resume()` in place of start: the two APIs serve different responsibilities.

## 22. Testing pause/resume with Spring Kafka

Integration tests should verify **actual container state and delivery**, not just verify a mock called `resume()`.

### 22.1. Basic pause-then-resume test

1. Start a test broker and a topic with data.
2. Create a listener container with a stable ID.
3. Send a few records and confirm the listener processed them.
4. Call `container.pause()`.
5. Wait for the pause event or actual paused state.
6. Send additional records while the container is paused.
7. Confirm no new deliveries occur within an appropriate observation window.
8. Call `container.resume()`.
9. Wait for the resume event or resumed state.
10. Confirm the waiting records are eventually processed.

In tests, use latches/await with timeouts instead of fixed `Thread.sleep(...)` calls that make tests flaky. The consumer may still be processing records from the previous poll before pause takes effect.

### 22.2. pauseImmediate test

1. Configure poll to return multiple records.
2. Enable `pauseImmediate=true`.
3. Request pause while the listener is processing the first record.
4. Confirm remaining records from the old poll are retained until resume per supported semantics.
5. Resume and confirm remaining records are delivered.
6. Verify offsets/processing results; do not assume any record is dropped.

### 22.3. Concurrency test

1. Use a multi-partition topic.
2. Configure container concurrency greater than 1.
3. Pause the parent container.
4. Wait for child consumers to apply the pause.
5. Resume the parent container.
6. Confirm partitions with valid assignments resume processing.
7. Observe `ConsumerResumedEvent` on each consumer when available.

### 22.4. Backpressure coordinator test

1. Simulate queue depth rising past `HIGH_WATERMARK`.
2. Confirm the coordinator requests pause.
3. Drop depth between high and low: container remains paused.
4. Drop below `LOW_WATERMARK` and confirm downstream is healthy.
5. Confirm the coordinator requests resume.
6. Activate `MANUAL_MAINTENANCE` and confirm queue recovery does not auto-resume against policy.
7. Verify an unhealthy dependency still keeps the container paused.

### 22.5. Restart/rebalance test

1. Pause the consumer while uncommitted records exist.
2. Restart or simulate a rebalance.
3. Confirm group assignments change per Kafka behavior.
4. Confirm the application's desired pause state is reapplied if needed.
5. After resume, verify uncommitted records are processed and idempotency remains intact.

## 23. Common mistakes

**Calling start() instead of resume().** When the container is still running and paused, use resume; start is a different lifecycle operation.

**Calling KafkaConsumer.resume() outside the consumer thread.** Bypasses container management and can violate thread-safety.

**Assuming resume takes effect on the same line of code.** The request is applied on the poll loop, so track applied state/events.

**Failing to identify the right listener ID.** The command may fail to find the container or control the wrong listener.

**Resuming one pod and thinking the entire group resumed.** The registry is process-local.

**Lacking a low-watermark.** Queue depth fluctuating around a single threshold causes pause/resume flapping.

**Multiple controllers calling resume independently.** One controller may bypass manual maintenance or downstream health.

**Resuming when pause is framework-managed.** Outstanding acknowledgments or backoff can keep the consumer paused.

**Thinking pause stops all in-flight record processing.** The listener may still be finishing records from the previous poll.

**Lacking idempotency.** Crashes/rebalances can still cause redeliveries regardless of pause/resume.

**Using resume to fix a poison pill.** Malformed payloads need an error handler/DLT, not toggling consumer pause.

**Using resume as an offset-commit command.** Resume does not confirm successful processing.

**Not watching backlog after resume.** The consumer is active again, yet may lack enough capacity to reduce lag.

## 24. Operational checklist

### Before resuming

- [ ] Identified the original cause of the pause.
- [ ] Downstream, queues, and database are sufficiently healthy.
- [ ] No manual maintenance flag remains active.
- [ ] Container has the right ID and is running.
- [ ] Checked partition-level pause and framework-managed pause if applicable.
- [ ] Have a plan to mitigate bursts when the backlog is large.

### When sending the request

- [ ] Use `MessageListenerContainer.resume()` rather than directly manipulating KafkaConsumer.
- [ ] Audit who/which controller issued the request.
- [ ] Do not treat the API return as confirmation that all child consumers have resumed.
- [ ] Have a mechanism to observe `ConsumerResumedEvent` or actual state.
- [ ] With multiple instances, distribute desired state to all required instances.

### After resuming

- [ ] Consumer actually transitions out of the paused state.
- [ ] New records or backlog are delivered if data is available.
- [ ] Lag and oldest record age trend downward.
- [ ] Queue depth and downstream latency stabilize.
- [ ] No pause/resume flapping occurs.
- [ ] Ack/commit and idempotency operate properly if redelivery occurs.
- [ ] If no progress is seen, inspect stop state, assignments, backoff, and listener errors.

## Conclusion

`resume()` is the operation that allows a Spring Kafka listener container to **continue consuming records after a pause request**. It is not start, seek, or offset commit. With `@KafkaListener`, applications typically look up the container by `id` from `KafkaListenerEndpointRegistry` and call `resume()`; actual state should be confirmed via `isConsumerPaused()` and application events rather than assuming the call takes effect instantaneously.

In a backpressure system, resume only after the conditions that caused the pause have been resolved, favoring high/low watermarks and a coordinator that unifies pause reasons. With high concurrency or multiple pods, observe individual consumers/instances and avoid post-resume bursts. Pause/resume helps stabilize inbound workload, but does not by itself guarantee processing, acknowledgment, or idempotency; therefore it must still be paired with proper error handling, DLT, accurate offset commits, and consumer lag monitoring for reliable recovery.
