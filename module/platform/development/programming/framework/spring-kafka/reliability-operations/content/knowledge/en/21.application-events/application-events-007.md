# ConsumerStoppedEvent

In Spring Kafka, the listener container manages the Kafka consumer lifecycle: initializing, joining the consumer group, polling, delivering records to the listener, committing offsets, and closing the consumer. A production application needs to know not only **whether records are processed successfully**, but also **whether the consumer is actually still operating**.

**ConsumerStoppedEvent** is an application event published by Spring Kafka when a consumer is stopped. It provides a lifecycle signal so the application can write logs, update metrics, trigger alerts, and analyze why the consumer stopped running. This event is particularly useful when a consumer stops due to abnormal errors such as authentication errors, transaction errors, or failing to find a valid offset.

Remember from the start: **ConsumerStoppedEvent is not a record retry mechanism, not an offset-commit callback, and does not automatically restart the consumer.** It is a signal for observing lifecycle state. Recovery requires combining the Kafka listener container, error handler, restart policy, and consumer group operations.

## 1. Where does ConsumerStoppedEvent sit in Spring Kafka?

A Spring Kafka process can create multiple listener containers, each having one or more actual consumers depending on concurrency.

    Spring Boot application
             |
             v
    KafkaListenerEndpointRegistry
             |
             +--- Container "orders"
             |         |
             |         +--- Child consumer 1
             |         +--- Child consumer 2
             |
             +--- Container "payments"
                       |
                       +--- Child consumer 3

Each consumer has its own lifecycle, even though the consumers may belong to the same consumer group. When a consumer stops and Spring Kafka publishes the corresponding event, Spring application event listeners can observe ConsumerStoppedEvent.

Common purposes:

- Distinguish normal consumer stops from error-driven stops.
- Detect producer fencing issues in transactional listeners.
- Alert when a consumer cannot maintain authentication.
- Record when a consumer stops due to having no valid offset.
- Observe application shutdown or scale-down.
- Investigate why consumer lag increases because the active consumer count dropped.
- Combine with other events to track listener container state.

ConsumerStoppedEvent does not replace Kafka AdminClient, consumer group metrics, or container health checks. It is **a local signal** inside the application JVM.

## 2. Distinguishing consumer, listener, and container

These three concepts are easily used interchangeably:

| Component | Responsibility | What to observe when stopping? |
|---|---|---|
| Kafka Consumer | Poll records, manage group membership and offsets | Is the consumer thread still running? |
| @KafkaListener method | Process a record or batch | Is business logic throwing exceptions? |
| KafkaMessageListenerContainer | Manage one Kafka consumer | Why did the consumer start/stop? |
| ConcurrentMessageListenerContainer | Manage multiple child containers | How many children are still running? |
| KafkaListenerEndpointRegistry | Manage containers created from @KafkaListener | Which listener containers by ID are running? |

An exception inside `@KafkaListener` **does not mean** ConsumerStoppedEvent will appear. DefaultErrorHandler may retry or recover successfully, keeping the consumer running.

Conversely, a consumer can stop during a normal shutdown without any business exception.

## 3. ConsumerStoppedEvent vs. other application events

Spring Kafka publishes many lifecycle-related events. Some common events:

| Event | Timing/meaning |
|---|---|
| ConsumerStartingEvent | Consumer is preparing to start |
| ConsumerStartedEvent | Consumer has started |
| ConsumerStoppingEvent | Consumer is preparing to stop |
| ConsumerStoppedEvent | Consumer has stopped; includes reason information |
| ContainerStoppedEvent | Container has stopped per its corresponding lifecycle |
| ConsumerPausedEvent | Consumer is actually paused |
| ConsumerResumedEvent | Consumer is resumed |
| ConsumerPartitionPausedEvent | A partition is paused |
| ConsumerPartitionResumedEvent | A partition is resumed |
| NonResponsiveConsumerEvent | Monitoring sees the consumer poll unresponsive for too long |
| ListenerContainerIdleEvent | Listener container received no records during the configured idle interval |

The events above are not all always published together, nor is an identical strict sequence guaranteed across every version and failure scenario.

**ConsumerStoppingEvent** and **ConsumerStoppedEvent** differ in timing. If you need to know the consumer is in the process of stopping, observe Stopping. If you need to record that the consumer's lifecycle has ended, use Stopped.

**ContainerStoppedEvent** reflects container lifecycle; ConsumerStoppedEvent reflects a specific consumer. In environments with multiple child consumers, they do not have a 1:1 ratio in all situations.

## 4. Meaning of the Reason attribute

ConsumerStoppedEvent provides the stop reason via `getReason()` in Spring Kafka versions supporting this API.

Common values of `ConsumerStoppedEvent.Reason` include:

| Reason | Interpretation | Investigation direction |
|---|---|---|
| NORMAL | Consumer ended via normal stop path | Shutdown, scale down, container.stop |
| ERROR | Consumer stopped due to an error outside normal processing | Kafka client, listener container, stack trace near stop time |
| FENCED | Transactional producer was fenced | transactional.id, duplicate identity, rolling deployment, zombie producer |
| AUTH | Authentication or authorization error caused consumer to stop | SASL/TLS, credentials, ACLs, broker |
| NO_OFFSET | Could not find a starting offset when policy requires a valid offset | consumer group offset, auto.offset.reset, retention |

The enum list and the conditions generating each Reason can change across Spring Kafka versions. In production, record the exact reason provided by the running version and cross-check exception logs rather than inferring root cause from the enum alone.

Reason is **a high-level classification**, not the full exception stack or complete proof of broker state.

## 5. NORMAL does not mean the application is always healthy

During a rolling deployment, the application receives SIGTERM, the Spring context closes, and listener containers stop cleanly. ConsumerStoppedEvent with Reason.NORMAL can be completely expected.

Example:

    Kubernetes scale down
            |
            v
    Spring context closes
            |
            v
    Listener container stops
            |
            v
    Consumer closes normally
            |
            v
    ConsumerStoppedEvent(NORMAL)

However, if a component in the application accidentally calls `stop()` on the container, the consumer can also stop in a lifecycle-normal way while being **undesired** by business operations.

Therefore:

- Reason.NORMAL does not prove the service is still consuming data.
- During deploy/scale, NORMAL can be treated as an expected signal.
- When no shutdown is planned, repeated NORMAL events may indicate containers are being stopped by application logic.
- To determine current health, check the registry, running consumer count, consumer lag, and readiness state.

Do not set critical pager alerts for every NORMAL event, yet do not ignore all NORMAL events if an application suddenly has no consumers left.

## 6. ERROR: Abnormal consumer stop

Reason.ERROR indicates the consumer stopped via an error path not handled as a normal shutdown.

Possible related causes:

- Exception outside the normal listener-processing loop.
- Kafka client or poll failure.
- Container lifecycle error.
- Unrecoverable error where the framework decides to stop the consumer.
- Error interaction with handlers, transactions, or dependent systems.

Do **not** deduce that every IllegalArgumentException or RuntimeException from a business listener produces ERROR. If the error handler retried, recovered, or skipped the error per policy, the consumer may still be running.

When receiving ERROR, investigate chronologically:

1. Identify the event's source container/consumer.
2. Find the first exception prior to the stop timestamp.
3. Check the consumer group and membership.
4. Check broker connectivity, polling, deserializer, authorization, and transactions.
5. Determine whether the container has a restart mechanism or stopped permanently.
6. Monitor committed offsets and lag to assess data impact.

Logging ConsumerStoppedEvent alone is not enough to reconstruct the cause; preserve trace/correlation with container logs from the same timestamp.

## 7. FENCED: Cause related to transactional producers

In a Spring Kafka application using Kafka transactions, the Kafka broker can fence an older transactional producer when another producer uses the same `transactional.id` with a newer producer epoch.

Example:

    Pod A creates producer transactional.id=orders-tx-1
               |
               v
    Pod A hits network partition without dying
               |
               v
    Pod B uses same transactional.id=orders-tx-1
               |
               v
    Broker fences Pod A's old producer
               |
               v
    Pod A cannot continue transactions as before

When the container stops due to producer fencing, ConsumerStoppedEvent can carry Reason.FENCED.

How to handle:

- Check `transaction-id-prefix` on each instance.
- Check whether old and new pods coexist during a rolling deployment.
- Verify whether `transactional.id` is assigned uniquely to each active producer.
- Look for `ProducerFencedException` or related exceptions in logs.
- Inspect producer cache/lifecycle management handled by Spring Kafka.
- Design restarts only after ensuring producer identities no longer collide.

Do not fix FENCED merely by restarting continuously. If transactional ID config remains duplicated, restarts can create a fencing loop and destabilize the consumer group.

Kafka fencing protects transaction correctness inside Kafka; side effects already executed outside Kafka such as databases and APIs must still be idempotent.

## 8. AUTH: Consumer stopped due to authentication or authorization

Reason.AUTH can appear when the consumer fails to authenticate with the broker or lacks permission for a required operation.

Some causes:

- Expired SASL username/password or token.
- Invalid or expired TLS certificate.
- ACL does not allow the consumer to read the topic or join the group.
- Broker changed security config while the client was not yet updated.
- Unsynchronized secret rotation rollout.
- Failure in an external authentication service.

Distinguish:

- **Authentication:** can the client prove its identity to the broker?
- **Authorization:** is the identity valid yet lacking permission to read the topic/group?

Spring Kafka supports retry configuration for certain authentication/authorization exceptions in supported versions, such as `authExceptionRetryInterval`. When this mechanism is configured, not every AUTH error immediately leads to ConsumerStoppedEvent; the consumer may retry per policy before stopping.

When receiving AUTH:

1. Check Kafka client and broker logs.
2. Verify secrets and certificates are mounted properly.
3. Verify topic/group ACLs.
4. Check the credential distribution system.
5. Never write usernames/passwords, tokens, or full security configs into event logs.
6. Only resume/restart once authentication conditions are fixed or a safe retry policy is in place.

## 9. NO_OFFSET: No valid starting point

A Kafka consumer group reads from the latest committed offset if that offset is still valid. If there is no committed offset or the current offset is no longer in the log, behavior depends on `auto.offset.reset`.

Common options:

- earliest: start from the earliest remaining offset.
- latest: start from the latest offset.
- none: do not automatically choose a new offset; can raise an error when no valid offset exists.

Example:

    Topic orders.events
    Retention deleted old records
    Group committed offset is no longer valid
              |
              v
    auto.offset.reset=none
              |
              v
    NoOffsetForPartitionException
              |
              v
    Consumer stops / ConsumerStoppedEvent(NO_OFFSET)

Another scenario is a new consumer group that has never committed offsets yet uses reset policy `none`.

Do not automatically fix this by setting `latest` in production if doing so skips unprocessed data. A business decision is needed on whether starting at earliest/latest is acceptable or data must be restored elsewhere.

Investigation steps:

- Check whether the group has a committed offset.
- Check that topic partitions exist and inspect current earliest/latest offsets.
- Determine whether retention expired the old offset.
- Check `auto.offset.reset` configuration.
- Determine the permitted recovery position per runbook.

## 10. Listening for ConsumerStoppedEvent with @EventListener

Spring Framework supports listening to application events with `@EventListener`. With Spring Kafka, you can write a simple bean:

~~~java
package com.example.kafka.monitoring;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStoppedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerStopLogger {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerStopLogger.class);

    @EventListener
    public void onConsumerStopped(ConsumerStoppedEvent event) {

        ConsumerStoppedEvent.Reason reason = event.getReason();

        if (reason == ConsumerStoppedEvent.Reason.NORMAL) {
            log.info(
                "Kafka consumer stopped normally; source={}",
                event.getSource()
            );
        }
        else {
            log.warn(
                "Kafka consumer stopped abnormally; reason={} source={}",
                reason,
                event.getSource()
            );
        }
    }
}
~~~

When ConsumerStoppedEvent is published by Spring Kafka via `ApplicationEventPublisher`, Spring delivers it to the registered listener.

`getSource()` is a Spring `ApplicationEvent` method suitable for recording event source identification. Do not assume `source` is a `KafkaConsumer` you can manipulate, and do not cast it to commit/seek.

If the system has multiple Kafka listener containers in the same application context, the observer can receive events from multiple containers. When designing per-listener alerts, resolve a stable identity according to the contract of your Spring Kafka version rather than relying solely on `source.toString()`.

## 11. Listening with ApplicationListener

Besides annotations, you can implement `ApplicationListener<ConsumerStoppedEvent>`:

~~~java
@Component
public class ConsumerStopObserver
        implements ApplicationListener<ConsumerStoppedEvent> {

    private final Logger log =
            LoggerFactory.getLogger(ConsumerStopObserver.class);

    @Override
    public void onApplicationEvent(ConsumerStoppedEvent event) {
        log.info(
            "ConsumerStoppedEvent observed: reason={}",
            event.getReason()
        );
    }
}
~~~

Both `@EventListener` and `ApplicationListener` are valid. Choose one style suited to the project structure to avoid recording metrics or sending alerts twice for the same event.

If the application needs to receive multiple Spring Kafka event types, you can place multiple `@EventListener` methods inside the same monitoring component, each handling one event type.

## 12. Using metrics instead of logs alone

ConsumerStoppedEvent is useful for counters classifying stop reasons.

Example with Micrometer:

~~~java
@Component
public class ConsumerStopMetrics {

    private final MeterRegistry meterRegistry;

    public ConsumerStopMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {
        String reason = event.getReason().name();

        meterRegistry.counter(
            "kafka.consumer.stopped",
            "reason", reason
        ).increment();
    }
}
~~~

The metric above is tagged by `reason`, a low-cardinality label. When using Prometheus, counter names may be normalized by registry conventions; check the actual displayed name on dashboards.

Do not use `eventId`, offset, UUID, or full exception messages as metric labels. Those values have high cardinality, increase storage costs, and can overload the metrics backend.

If you need labels for listener ID or group ID, retrieve them from stable configuration/container metadata via the API of your version. Do not infer group ID from topic names or from source string formats not guaranteed stable by documentation.

Counters only tell how many stops occurred; they do not tell **how many consumers are currently alive**. Therefore, supplement them with running/assignment metrics and container state.

## 13. Caution with concurrent listeners

When Spring Kafka uses `ConcurrentMessageListenerContainer` with concurrency greater than 1, each child container usually manages its own consumer.

Example:

    @KafkaListener(id="orders", concurrency=4)
               |
               v
    Parent container
       |
       +--- Child 0 -> Consumer A
       +--- Child 1 -> Consumer B
       +--- Child 2 -> Consumer C
       +--- Child 3 -> Consumer D

When stopping the whole container, multiple ConsumerStoppedEvent occurrences can be observed, typically corresponding to the stopped child consumers.

Do not write logic like:

    Any ConsumerStoppedEvent received
        => entire "orders" listener has stopped

One child consumer stopping does not prove the parent container or remaining children have stopped. Similarly, counting one NORMAL event as an application shutdown can skew statistics when concurrency changes.

Distinguish:

- Stop event count of child consumers.
- Count of currently running consumers.
- Parent container state.
- Number of assigned partitions.
- Consumer lag by partition and consumer group.

When you want to alert on "entire listener stopped," inspect container-level state or use ContainerStoppedEvent as required, not just a single ConsumerStoppedEvent.

## 14. Checking container state via KafkaListenerEndpointRegistry

Spring Kafka provides `KafkaListenerEndpointRegistry` to look up listener containers declared from `@KafkaListener` by ID.

~~~java
@Service
public class KafkaContainerStatusService {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaContainerStatusService(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isOrdersListenerRunning() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        return container != null && container.isRunning();
    }
}
~~~

Key imports:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;
~~~

For lookup to work, `@KafkaListener` must declare the matching `id="ordersListener"`.

Timing note: if reading `isRunning()` right **inside** the ConsumerStoppedEvent callback, the parent container may still be finishing its stop process or other children may still be stopping. To confirm the final state, check again after lifecycle completion or observe ContainerStoppedEvent.

`isRunning()` reflects container lifecycle; it does not mean the consumer just processed records successfully, partitions are assigned, or lag is acceptable. Health requires multiple signals.

## 15. On which thread is the event published?

Spring Kafka application events are usually published from the thread managing the consumer/container. With the default synchronous `ApplicationEventMulticaster`, the `@EventListener` method can run directly on the event-publishing execution path.

Consequences:

- Slow handlers can prolong the consumer stopping step.
- A hanging network API inside the handler can obstruct graceful shutdown.
- Unhandled exceptions in the handler can disrupt the event-publishing path.
- Do not perform heavy blocking operations just to send alerts.
- `KafkaConsumer` APIs must only be called from the owning consumer thread; never hand the reference to another thread.

Spring Framework allows swapping `ApplicationEventMulticaster` or using async mechanisms. When events dispatch asynchronously, callbacks can run on another thread; do **not** use async callbacks to manipulate `KafkaConsumer` via commit, seek, pause, or poll.

Dangerous handler example:

~~~java
@EventListener
public void onStopped(ConsumerStoppedEvent event) {
    // Anti-pattern: network operation that can wait for minutes.
    remoteIncidentApi.sendFullDiagnosticReport(event);
}
~~~

Keep callbacks fast: record metrics, write brief logs, or hand off lightweight notifications to a separately managed async mechanism with bounded queues and timeouts.

## 16. Safer pattern for forwarding signals to an alerting system

If abnormal state must be pushed to an alerting service, decouple **receiving the application event** from **sending network notifications**.

Illustrative pattern:

~~~java
public record ConsumerStopSignal(
        String reason,
        String applicationInstance,
        Instant occurredAt) {
}

public interface ConsumerStopSignalQueue {
    boolean offer(ConsumerStopSignal signal);
}

@Component
public class ConsumerStopEventAdapter {

    private final ConsumerStopSignalQueue queue;
    private final String instanceId;

    public ConsumerStopEventAdapter(
            ConsumerStopSignalQueue queue,
            @Value("order-service") String instanceId) {

        this.queue = queue;
        this.instanceId = instanceId;
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {

        if (event.getReason() == ConsumerStoppedEvent.Reason.NORMAL) {
            return;
        }

        ConsumerStopSignal signal = new ConsumerStopSignal(
            event.getReason().name(),
            instanceId,
            Instant.now()
        );

        boolean accepted = queue.offer(signal);

        if (!accepted) {
            // Record dropped-notification metric for operations visibility.
            // Do not block indefinitely in the consumer event callback.
        }
    }
}
~~~

This is a design pattern: `ConsumerStopSignalQueue` is an interface the application must implement, such as a bounded queue with a dedicated worker or an internal event-publishing mechanism. In production, import `Instant`, `Value`, `EventListener`, `Component`, and related types.

If an in-RAM queue is lost when the process dies, unsent alerts can also be lost. For severe incidents, combine independent signals such as Kubernetes readiness, Prometheus metrics, or external consumer group checks outside the JVM. Never treat notifications from the dying process itself as the sole alerting channel.

## 17. Do not blindly restart the container directly inside the callback

When receiving ConsumerStoppedEvent with ERROR or FENCED, a naive idea is calling `start()` immediately:

~~~java
@EventListener
public void onStopped(ConsumerStoppedEvent event) {
    registry.getListenerContainer("ordersListener").start();
}
~~~

This is an **anti-pattern**, not a recommended approach. It creates multiple issues:

1. The container may still be finishing its stop lifecycle.
2. The event may belong to one child while the parent container is still running.
3. `Reason.FENCED` or `AUTH` may reflect unfixed configuration.
4. Calling start/stop right on the event thread can cause hard-to-control lifecycle interactions.
5. Continuous restarts create rebalance storms and mask the real cause.

If self-recovery is needed, use a separate supervisor:

- Receive the stopped signal.
- Inspect container/state and root cause.
- Classify errors as retryable or non-retryable.
- Apply backoff, restart attempt limits, and cooldowns.
- Ensure no other process/controller is managing restarts simultaneously.
- Check credentials, broker status, or transactional IDs.
- Emit metrics and alerts if failures persist.

In Kubernetes deployments, readiness/liveness policies and deployment controllers handle part of restarting. Avoid letting an in-JVM supervisor and the orchestrator create two uncoordinated restart loops.

## 18. Sample action classification policy

| Reason | Immediate reaction | Recovery reaction |
|---|---|---|
| NORMAL | Info-level log, confirm whether planned shutdown | Do not restart during scale down/deploy |
| ERROR | WARN/ERROR log, increment metric, inspect exception | Can restart with backoff if transient error |
| FENCED | Alert on producer transaction, inspect identity | Fix transactional.id/prefix and lifecycle before recovering |
| AUTH | Alert on authentication and permissions config | Check secret/ACL; controlled retry after fixing |
| NO_OFFSET | Stop consumption, verify committed offset/retention | Decide reset position per business rules |
| New/unknown reason | Record verbatim, do not ignore | Apply safe default policy, check framework version |

Do not treat `Reason.ERROR` as always safe to auto-restart. For instance, if a listener stopped due to a recurring configuration error, immediate restarts only generate extra traffic, logs, and consumer group instability.

Similarly, do not blindly reset offsets to `latest` on `NO_OFFSET` if the service has a zero-data-loss requirement.

## 19. ConsumerStoppedEvent does not replace error handlers

Spring Kafka error handling aims to handle **record** errors. ConsumerStoppedEvent describes **consumer lifecycle** state.

Example:

    Listener reads OrderCreated
            |
            v
    Database timeout
            |
            v
    DefaultErrorHandler retry
            |
            v
    Second attempt succeeds
            |
            v
    Consumer continues polling

In this scenario, ConsumerStoppedEvent may not appear at all because the consumer never stopped.

If a record cannot be processed, DefaultErrorHandler can call `DeadLetterPublishingRecoverer` to publish to the DLT and continue with the next record. That is still not a consumer stopped event.

Conversely, when a consumer loses permission to read a topic, error-handler callbacks cannot solve the problem because the error occurs at the consumer/broker authorization layer. `ConsumerStoppedEvent.AUTH` tells operations that the consumer lifecycle stopped along the authentication/authorization failure path.

Monitor in parallel:

- Listener processing failures.
- Retries and recovery/DLT.
- ConsumerStoppedEvent and reason.
- Consumer lag, assignment, and offset commits.
- Kafka client health and broker connectivity.

## 20. ConsumerStoppedEvent and Kafka transactions

With a transactional listener container, there is an important boundary:

    Consumer polls input
          |
          v
    Begin Kafka transaction
          |
          v
    Listener processes and sends output
          |
          v
    Commit output + source offsets

If the transactional producer is fenced or the transaction cannot proceed, the container may stop the consumer and publish `ConsumerStoppedEvent.FENCED` or a Reason matching the failure path.

Kafka transactions can guarantee atomicity between Kafka outputs and consumer offsets when properly configured. However:

- ConsumerStoppedEvent does not itself commit or abort transactions.
- A stopped event does not confirm whether a specific transaction committed.
- If a transaction aborts, input can be safely redelivered from the committed offset.
- If a database/API outside Kafka already executed a side effect, it does not automatically roll back with Kafka.
- Receiving a FENCED event does not replace checking producer ID/epoch and container transaction logs.

When investigating incidents, observe transaction commit/abort metrics, consumer stop counts, group generations, and duplicate handling via eventId.

## 21. Offsets, acknowledgment, and redelivery possibility

A consumer stopping does not prove every record was committed.

Example:

    Committed offset = 200
    Consumer polls records 200..209
    Listener processes successfully through 204
    Consumer stops abnormally

If the container has not committed offsets past record 204, a new consumer can re-read starting from 200. If some records were committed according to AckMode, the replay range differs.

Therefore:

- Do not infer commit state from ConsumerStoppedEvent.
- Do not use the stopped event as a spot to "finish acking" incomplete records.
- Do not call `KafkaConsumer.commitSync()` or `seek()` from an event listener to patch state.
- Always verify actual committed offsets when analyzing data loss/duplicates.
- Design idempotent side effects keyed by eventId or unique business key.
- Distinguish between the consumer polling a record and the listener processing and committing it successfully.

When a process is killed abruptly, ConsumerStoppedEvent may not even be published. Recovery must rely on committed offsets and durable processing contracts, not cleanup callbacks.

## 22. ConsumerStoppedEvent vs. rebalance

Rebalance is the process where a Kafka consumer group redistributes partitions. A running consumer can lose some partitions or receive new ones without stopping the entire consumer.

Rebalance-related callbacks:

- `onPartitionsAssigned`.
- `onPartitionsRevoked`.
- `onPartitionsLost`.

Meanwhile, ConsumerStoppedEvent reports the consumer-stop lifecycle.

Example:

    Rebalance:
      Consumer A loses P2, still processes P0/P1
      => does not necessarily emit ConsumerStoppedEvent

    Consumer shutdown:
      Consumer A closes and leaves group
      => may emit ConsumerStoppedEvent(NORMAL)

Do not use ConsumerStoppedEvent to replace `onPartitionsLost` when you need to discard partition-local state or fence work from a previous owner. Lost ownership can occur while the consumer thread keeps running.

Similarly, receiving ConsumerStoppedEvent does not provide the exact list of revoked partitions; you need rebalance callbacks or assignment metrics for analysis.

## 23. ConsumerStoppedEvent is not the only alerting condition

A system cannot rely solely on events from within the JVM itself to know a consumer died.

Several situations do not guarantee the event is published or received:

- JVM receives SIGKILL or runs out of memory and crashes abruptly.
- Container/pod is killed before Spring context shutdown.
- Power loss or node eviction from the cluster.
- Process crashes before `ApplicationEventListener` is invoked.
- Application event handler fails or is unregistered.
- Async alert delivery path drops messages when the JVM dies.

Therefore, production must have **external monitoring**:

1. Consumer group member count/assignment.
2. Consumer lag and offset commit rate.
3. Listener container running state/readiness.
4. Pod/process health and restart count.
5. Broker/client connection metrics.
6. ConsumerStoppedEvent occurrences recorded while the process was alive.

The event is helpful for analyzing **why** a consumer stopped when the framework had time to run lifecycle hooks; external systems must detect **when a consumer no longer exists** even without an event.

## 24. Readiness and liveness must be distinguished

When a consumer stops abnormally, the web application can still return HTTP 200 because Tomcat/Netty is still running. Yet a healthy API does not mean a healthy consumer.

Readiness can evaluate:

- Mandatory listener containers are running.
- Consumer group holds enough assignments to handle required workload.
- Consumer has no unrecovered auth/fenced errors.
- Committed offsets advance when input traffic is present.
- Lag or oldest record age stays within SLO thresholds.

Liveness should not automatically fail just because a consumer temporarily rebalances; doing so can trigger a restart storm. Conversely, a permanently failed consumer may require a process restart if the application has no safe listener-restart mechanism.

A good policy clearly separates:

| Question | Source |
|---|---|
| Is the JVM/process alive? | Liveness probe/process metrics |
| Is the consumer eligible for traffic? | Readiness + registry + group assignment |
| Why did the consumer stop? | ConsumerStoppedEvent.Reason + logs |
| Is data falling behind? | Consumer lag, oldest age, commit rate |
| Are records failing to process? | Error handler, DLT, retry metrics |

## 25. Observing multiple stop/start cycles in the same window

A consumer can go through a sequence:

    ConsumerStartingEvent
             |
             v
    ConsumerStartedEvent
             |
             v
    ConsumerStoppedEvent(ERROR)
             |
             v
    Supervisor restarts after backoff
             |
             v
    ConsumerStartingEvent
             |
             v
    ConsumerStartedEvent

Looking only at the last event makes it hard to spot a restart loop. Keep a short history of lifecycle transitions with timestamps and stable identifiers.

Metrics to observe:

- Number of consumer stops in 5 or 15 minutes.
- Breakdown of ERROR/FENCED/AUTH/NO_OFFSET.
- Time from stopped to next started.
- Consecutive restart cycles.
- Consumer lag at stop time and after start.
- Number of partitions with no active consumer.
- Duplicate side effects after redelivery.

You can alert when a mandatory container stays not running beyond a threshold duration, or when N abnormal stops occur within a window. The duration and N must be grounded in SLOs rather than treating every single event as a system-wide outage.

## 26. Designing useful and safe logging

A log message for ConsumerStoppedEvent should contain the following fields if obtainable from valid metadata and configuration:

    event_type=ConsumerStoppedEvent
    timestamp=...
    application=order-service
    instance=order-service-pod-3
    listener_id=ordersListener
    reason=FENCED
    source=...
    severity=WARN

Do not log the entire Consumer or credentials, and do not serialize the raw event object directly to logs.

If the system uses JSON structured logging, build an adapter converting the Kafka event into a lightweight record. Internal framework events are not a stable data contract to publish directly externally.

For exception context, you typically need to consult logs prior to the stopped timestamp. `ConsumerStoppedEvent.Reason` does not replace the root error's stack trace.

Correlate by application instance, listener ID, and occurrence timestamp. Do not use offsets or eventIds as metric labels; when investigating a specific record, use logs with appropriate detail.

## 27. Testing ConsumerStoppedEvent reception

You can verify a Spring context receives the expected event with a test observer, then test the lifecycle against a test Kafka broker (EmbeddedKafka or Testcontainers).

Simple observer template:

~~~java
@Component
public class StoppedEventRecorder {

    private final BlockingQueue<ConsumerStoppedEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void record(ConsumerStoppedEvent event) {
        events.offer(event);
    }

    public ConsumerStoppedEvent nextEvent(Duration timeout)
            throws InterruptedException {

        return events.poll(
            timeout.toMillis(),
            TimeUnit.MILLISECONDS
        );
    }
}
~~~

Key imports:

~~~java
import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStoppedEvent;
import org.springframework.stereotype.Component;
~~~

The example uses an unbounded queue solely to illustrate a test recorder. In production, never retain full application event objects indefinitely in memory; use bounded queues and retain only necessary metadata.

Single-listener test scenario:

1. Initialize application context, Kafka listener container, and test broker.
2. Wait for the consumer to start and receive assignment per test conditions.
3. Call stop on the container from the test thread (not from a consumer event callback).
4. Await ConsumerStoppedEvent via the recorder.
5. Verify the reason for normal shutdown.
6. Verify the container is ultimately not running.
7. Restart per lifecycle test and verify the listener resumes polling.

When concurrency > 1, the recorder may receive multiple events. Tests should not hard-assert "exactly one event" when a parent container manages multiple child consumers.

## 28. Testing abnormal reasons

Not every reason is easy to reproduce with a unit test. Some require an integration environment or fault injection.

### 28.1. ERROR

Trigger an error considered fatal at the consumer/container level by the running Spring Kafka version. Observe events and logs near the stop timestamp; do not use a business error that DefaultErrorHandler recovers from and expect the consumer to stop.

### 28.2. AUTH

Use a test broker configured with SASL/TLS or ACLs to induce auth/authz failures, and verify auth retry mechanics if enabled. Assert the stopped event only when the consumer actually stops; a transient exception does not guarantee a stopped event.

### 28.3. FENCED

Use controlled producer transactional IDs to simulate fencing per Kafka contracts, or induce intentional conflict in an isolated test. Never run this scenario against production transactional IDs.

### 28.4. NO_OFFSET

Create a new consumer group, set `auto.offset.reset=none`, and provide no valid committed offset. Observe the error path and reason on the running version. Ensure the test environment has no leftover group offset that would prevent reproduction.

### 28.5. JVM crash

Kill the process to confirm **no assumption is made that callbacks will fire**. Tests must rely on external health and consumer group recovery. This scenario proves the design boundary of application events.

When writing tests, prioritize asserting **container state, actual events, and offset/lag outcomes** rather than relying solely on callback ordering that a specific version happens to produce.

## 29. Operational scenario: ConsumerStoppedEvent yet lag remains 0

This can happen because:

- The topic currently has no new records.
- The consumer group has multiple members; one child stopped while other members continue processing.
- The consumer committed all data before stopping.
- Topic retention/offsets currently create no backlog.
- Lag metrics are not updated or are stale.

Therefore, zero lag does not prove the consumer is operating normally. Check container running state and group membership.

Conversely, rising lag does not necessarily emit ConsumerStoppedEvent: the consumer may still be running yet processing slowly, paused, blocked in retries, hitting a hot partition, or experiencing downstream overload.

The two signals answer two different questions: **consumer lifecycle** and **data consumption progress**.

## 30. Operational scenario: Duplicate events or events missing from monitoring

If metrics/logs receive many ConsumerStoppedEvent occurrences:

- Check whether there are multiple child consumers/concurrency.
- Check whether a deployment is stopping multiple pods simultaneously.
- Check whether two `@EventListener` beans handle the same event.
- Check whether a supervisor is causing a continuous stop/start loop.
- Distinguish events across multiple application instances.

If monitoring sees no event even though the group lost a consumer:

- The process may have died before publishing the event.
- The app context closed too early.
- The listener bean is outside component scan.
- `ApplicationEventMulticaster` was altered unexpectedly.
- The callback handler threw an exception or the alert queue dropped data.
- The consumer never ran in the application instance being observed.

External monitoring gaps must be solved using broker/orchestrator signals, not by assuming the event definitely existed and merely failed to send.

## 31. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Treating every ConsumerStoppedEvent as an error | False alerts during normal shutdown/scaling | Classify by reason and planned lifecycle |
| Treating NORMAL as definitely healthy | Misses unexpected container stops | Combine registry and business SLOs |
| Treating event as whole parent container stopped | Misreads state when concurrency > 1 | Track children and parent separately |
| Calling restart directly in event handler | Lifecycle races, restart loops, rebalance storms | Separate supervisor with backoff/cooldown |
| Blocking HTTP alerts in callback | Slow or hung container stop | Lightweight, bounded queue with timeouts |
| Using KafkaConsumer from async event listener | Thread-safety violation | Never touch Consumer outside owner thread |
| Committing offsets on stopped event | May acknowledge unprocessed records | Let container/transactions manage offsets |
| Not tracking FENCED/AUTH/NO_OFFSET | Misses hard-to-self-heal config errors | Reason-based alerts with runbooks |
| Using event alone as liveness | Misses JVM crashes/SIGKILL | External health, group metrics |
| Putting full exceptions in metric labels | High cardinality and data leaks | Fixed reason label; controlled exception logs |
| Testing only one consumer when prod has high concurrency | Wrong expected event counts | Test multi-child listener lifecycle |
| Expecting listener business exceptions to always stop consumers | Misunderstands error handler | Separate record errors from lifecycle stops |

## 32. Runbook upon seeing an abnormal ConsumerStoppedEvent

When detecting an unplanned consumer stop, follow this sequence:

1. **Identify scope:** application, instance, listener ID, timestamp, and reason.
2. **Assess impact:** is the parent container running, does the group still have members, what are lag/oldest age?
3. **Find root error:** inspect logs before the stopped event, separating consumer/client/transaction/auth causes.
4. **Confirm recent changes:** deployments, scaling, secret rotation, ACLs, broker rollouts, topic retention.
5. **Check offsets:** does the group have valid offsets, are there uncommitted records requiring redelivery?
6. **Classify recovery:** is the error retryable or does configuration/data need fixing?
7. **For FENCED:** verify transaction IDs and producer lifecycle before restarting.
8. **For AUTH:** verify certificates, secrets, and permissions; avoid logging confidential data.
9. **For NO_OFFSET:** determine the reset position with an explicit business decision.
10. **If restarting:** use backoff, prevent multiple controllers from restarting simultaneously, and monitor started events.
11. **After recovery:** confirm the listener receives new records, offsets advance properly, and no unexpected duplicate side effects occur.
12. **Document the incident:** add metrics, alerts, and tests to detect it earlier next time.

Do not use `auto.offset.reset=latest` or manually commit offsets as a "quick recovery hack" before knowing whether unprocessed data exists. Doing so can lose work the consumer group was supposed to process.

## 33. Production adoption principles

- ConsumerStoppedEvent is a consumer lifecycle signal, not a record retry mechanism.
- Listen with `@EventListener` or `ApplicationListener` in the Spring context.
- Use `getReason()` to classify NORMAL, ERROR, FENCED, AUTH, and NO_OFFSET as supported by your version.
- Do not infer complete root cause from the enum alone; inspect Kafka client/container logs.
- In concurrent containers, distinguish individual child consumers from the parent container.
- Do not use stopped callbacks to commit offsets, seek, or acknowledge records late.
- Do not block the event thread with network calls or long processing.
- When events dispatch asynchronously, never manipulate KafkaConsumer from another thread.
- Use a supervisor and backoff if restarting is needed; do not restart immediately on every stop.
- For FENCED, fix transactional producer identity and lifecycle before retrying.
- For AUTH, check credentials/ACLs and auth retry policies.
- For NO_OFFSET, choose reset positions according to data policy.
- Combine the event with container running state, consumer group member count, lag, and oldest record age.
- Ensure external monitoring still detects process crashes even without events.
- Test normal shutdown, concurrent children, auth/fenced/no-offset errors, and restart capability.

**ConsumerStoppedEvent gives a Spring Kafka application visibility into the exact moment a consumer stops operating along with its stop reason classification.** Used properly, this event is valuable input for logging, metrics, alerting, and runbooks. Actual reliability still depends on committed offsets, recovery mechanisms, container lifecycles, producer transaction fencing, and external monitoring outside the JVM when a process stops abruptly.
