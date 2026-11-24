# ConsumerStoppedEvent

`ConsumerStoppedEvent` is an application event published by **Spring Kafka** when a Kafka consumer belonging to a listener container **has stopped operating**. This event helps applications observe the consumer lifecycle, identify the reason for stopping, and issue alerts or controlled recovery decisions.

In systems running multiple consumer threads, one consumer stopping does not mean the entire listener container has stopped. `ConcurrentMessageListenerContainer` can manage multiple child consumers and each consumer may terminate for its own reason. Therefore, when handling `ConsumerStoppedEvent`, distinguish **consumer-level events**, **container-level events**, **consumer group rebalances**, and **offset progress**.

This document explains the event's meaning, `Reason` values, how to register listeners in Spring, relationships with Kafka transactions, graceful shutdown, restart policies, observability, and incident runbooks.

## 1. Where does ConsumerStoppedEvent appear in the lifecycle?

The Spring Kafka listener container manages the `poll()` loop, dispatches records to `@KafkaListener` methods, and coordinates acknowledgements/commits. A typical lifecycle includes:

1. Container initializes the Kafka consumer and consumer thread.
2. Consumer joins the group, receives assignment, and begins `poll()`.
3. Container invokes listener to process records, retry, or recover on errors.
4. Offsets are committed per `AckMode` or transaction policy when eligible.
5. Container is requested to stop, or the consumer hits an error forcing it to stop.
6. Consumer cleans up resources, closes the client, and ends the processing loop.
7. Spring Kafka publishes lifecycle events, including `ConsumerStoppedEvent`.

~~~mermaid
sequenceDiagram
    participant A as Application / orchestration
    participant C as Listener container
    participant K as Kafka consumer thread
    participant E as Spring event observer
    A->>C: start()
    C->>K: Create consumer and start polling
    K->>K: Subscribe, poll, process records
    alt Normal stop
        A->>C: stop()
        C->>K: Request termination
    else Error forcing consumer stop
        K->>K: Exception or stop condition
    end
    K->>K: Cleanup and close consumer
    C->>E: ConsumerStoppedEvent(reason)
    E-->>C: Record event, metric, or recovery signal
~~~

The diagram illustrates the logical flow. Exact ordering between cleanup, auxiliary events, and async callbacks depends on the Spring Kafka version and application event multicaster configuration.

### What must NOT be inferred from the event?

A `ConsumerStoppedEvent` does not by itself prove:

- All child consumers of the parent container have stopped.
- The entire Spring Boot application is shutting down.
- The consumer group has finished rebalancing.
- The last record processed successfully.
- The last offset was definitely committed.
- Kafka transactions or database transactions committed.
- No background workers remain processing previously received data.
- Incomplete records will not be redelivered.

It is a **lifecycle signal**, not a certification of business success.

## 2. Distinguishing closely related events

Spring Kafka provides multiple application events; they describe different moments and scopes.

| Event | Scope | Purpose |
|---|---|---|
| `ConsumerStartingEvent` | Consumer | Observe when consumer initialization begins. |
| `ConsumerStartedEvent` | Consumer | Record that the consumer has started operating. |
| `ConsumerStoppingEvent` | Consumer | Observe the step where the consumer prepares to stop. |
| **`ConsumerStoppedEvent`** | **Consumer** | **Record that the consumer stopped and why.** |
| `ContainerStoppedEvent` | Container | Know the listener container reached stopped state. |
| `ConsumerFailedToStartEvent` | Consumer/container | Detect consumers failing to start within time bounds. |
| `NonResponsiveConsumerEvent` | Polling health | Detect consumers not responding/polling as expected. |
| `ListenerContainerIdleEvent` | Listener/container | Detect idle consumers, not stopped consumers. |
| Rebalance callback | Topic/partition | Know partitions assigned, revoked, or lost ownership. |

Exact classes, constructors, and event properties depend on the Spring Kafka version. When writing API-dependent code, match the exact version your project runs.

### ConsumerStoppedEvent vs ContainerStoppedEvent

Example of a listener with `concurrency=3`:

~~~text
Parent container: ordersListener
    Child consumer 0: thread A
    Child consumer 1: thread B
    Child consumer 2: thread C

Stop entire container:
    A stops -> ConsumerStoppedEvent
    B stops -> ConsumerStoppedEvent
    C stops -> ConsumerStoppedEvent
    Container finishes -> ContainerStoppedEvent
~~~

Thus, there can be multiple `ConsumerStoppedEvent`s during one valid shutdown. Avoid paging separate incident alerts for each `NORMAL` event while the application is rolling-deploying.

Conversely, receiving a single `ConsumerStoppedEvent` is insufficient to assert the entire container stopped. Check `ContainerStoppedEvent` or actual container status if the goal is coordinating parent-level lifecycle.

## 3. Reason: why did the consumer stop?

`ConsumerStoppedEvent` has a `getReason()` method representing the stop cause classified by Spring Kafka. Common values in Spring Kafka lines supporting this mechanism include:

| Reason | Meaning | First investigation direction |
|---|---|---|
| `NORMAL` | Consumer stopped along normal branch | Correlate stop command, shutdown, rolling deployment. |
| `ERROR` | Consumer stopped due to an error preventing normal continuation | Check root exception, container, and broker logs. |
| `FENCED` | Stop related to a fenced transactional producer | Check `transactional.id`, producer epoch, and deployment overlap. |
| `AUTH` | Stop due to authentication/authorization failure | Check credentials, TLS/SASL, and ACLs. |
| `NO_OFFSET` | No valid offset position found when policy disallows auto-reset | Check group committed offsets, retention, and `auto.offset.reset`. |

Check the enum in your actual Spring Kafka version because the list and classification can evolve. Not every exception from `@KafkaListener` produces `ERROR`. A listener error handled by `DefaultErrorHandler` via retry/DLT may not stop the consumer.

**Reason is only a lifecycle-level classification**, not a replacement for exception stack traces. Specifically, `FENCED` does not guarantee duplicate IDs between two pods; `AUTH` does not immediately tell whether credentials are wrong or ACLs are missing; `ERROR` does not tell exactly which record stopped the consumer.

## 4. Registering @EventListener for ConsumerStoppedEvent

A Spring application context can receive the event via `@EventListener`:

~~~java
@Component
public class KafkaLifecycleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaLifecycleObserver.class);

    @EventListener
    public void handleStopped(ConsumerStoppedEvent event) {
        log.warn(
                "Kafka consumer stopped: reason={}, sourceType={}",
                event.getReason(),
                event.getSource().getClass().getSimpleName());
    }
}
~~~

Imports include `org.springframework.kafka.event.ConsumerStoppedEvent`, `org.springframework.context.event.EventListener`, `org.springframework.stereotype.Component`, and SLF4J logger.

Because the handler only logs, there is little risk of interfering with the lifecycle. In production, correlate instance ID, listener ID, group ID, and timestamp via the actual APIs/metadata your Spring Kafka version provides.

### Classifying by Reason

~~~java
@EventListener
public void handleStopped(ConsumerStoppedEvent event) {
    ConsumerStoppedEvent.Reason reason = event.getReason();

    switch (reason) {
        case NORMAL:
            log.info("Kafka consumer stopped normally");
            break;
        case FENCED:
            log.error("Transactional producer fenced");
            break;
        case AUTH:
            log.error("Kafka authentication/authorization problem");
            break;
        case NO_OFFSET:
            log.error("No valid starting offset");
            break;
        case ERROR:
            log.error("Kafka consumer stopped due to error");
            break;
        default:
            log.warn("Kafka consumer stopped, reason={}", reason);
    }
}
~~~

The snippet illustrates handling semantics, not a complete restart controller. With enums varying across versions, re-check supported values. Never rely solely on `reason` to auto-reset offsets or rotate credentials.

### Counting stop events with Micrometer

~~~java
@Component
public class ConsumerStopMetrics {

    private final MeterRegistry registry;

    public ConsumerStopMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    @EventListener
    public void record(ConsumerStoppedEvent event) {
        registry.counter(
                "kafka.consumer.stopped.total",
                "reason",
                event.getReason().name()
        ).increment();
    }
}
~~~

The example assumes Micrometer `MeterRegistry` is configured. This counter counts **published event occurrences**, not the current number of stopped consumers. To measure current health, combine container/group state with started/assigned signals.

## 5. Event handlers may run on the consumer thread

Spring `ApplicationEventMulticaster` normally publishes events synchronously by default. Thus `@EventListener` may execute on the very thread publishing the event, which for Kafka lifecycle is often near the consumer/container thread.

Operational consequences:

- A long-blocking handler can prolong consumer stop/cleanup duration.
- An exception thrown from the handler can complicate the application event flow.
- Calling synchronous lifecycle operations again while the container is still stopping can cause races or deadlocks.
- Handlers should not perform database/network I/O without timeouts.
- Never use the event to reprocess records or manually commit offsets.

If the application configures an async multicaster, event handlers may run on another executor. In that case, even more strictly, never assume a Kafka `Consumer` reference can be operated on from the handler's thread.

### Safe event handling principles

1. Log, emit metrics, or update lightweight internal state.
2. Extract necessary metadata and signal a remediation service if needed.
3. Do not hold long-lived references to containers/consumers just for background workers.
4. Do not call `Thread.sleep` waiting for Kafka recovery.
5. Do not directly restart every consumer from callbacks.
6. If containers must be controlled, let a controller with state checks and backoff manage it.

`ConsumerStoppedEvent` is where you **detect and notify** state, not where you execute every recovery action.

## 6. NORMAL: intentional consumer stop

`NORMAL` typically corresponds to a planned application/container stop:

- Spring Boot is shutting down.
- The orchestrator asks a pod to terminate during a rolling deployment.
- The application calls `stop()` on the listener container.
- Operations scales down the workload.
- A maintenance workflow intentionally stops the consumer.

A `NORMAL` event matching a deployment window usually needs no paging. Still, correlate it with remaining consumer count and lag; if a workload stops without a replacement instance, backlog can grow.

### Graceful shutdown requires more signals

During a planned stop, verify:

- Were in-progress records completed?
- Were acknowledgements committed per policy?
- Were open Kafka transactions committed/aborted?
- Are background workers still mutating data after the container stopped?
- Did the consumer group redistribute partitions to active members?

`ConsumerStoppedEvent(NORMAL)` does not answer all those questions. It only records that the consumer stopped along a flow Spring Kafka classifies as normal.

## 7. FENCED: transactional producer lost authority

Transactional Kafka producers have a `transactional.id` and producer epoch. When a new producer initializes with the same valid ID, the Kafka coordinator can fence the older-generation producer. The old producer encounters `ProducerFencedException` or a producer epoch error on its next transactional operation.

In a Spring Kafka transactional listener, this situation can lead to a `ConsumerStoppedEvent` with reason `FENCED`.

~~~mermaid
sequenceDiagram
    participant A as Pod A - old producer
    participant K as Transaction coordinator
    participant B as Pod B - new producer
    participant E as ConsumerStoppedEvent observer
    A->>K: transactional.id=X, epoch E1
    Note over A: A pauses or loses connectivity
    B->>K: initTransactions ID=X
    K-->>B: epoch E2
    A->>K: commit transaction with E1
    K-->>A: Producer fenced
    A->>E: ConsumerStoppedEvent(FENCED)
    E->>E: Log and forward remediation signal
~~~

A single fencing of an old producer during replacement can be valid protection. Repeated fencing across healthy replicas usually points to a `transactionIdPrefix` collision or producer lifecycle issue.

### Handling FENCED

1. Record the instance, `transactional.id`/prefix, and exception timestamp.
2. Check all replicas/factories that could generate the same ID.
3. Correlate rollout overlap and unstopped old processes.
4. Do not reuse a fenced producer.
5. Inspect transaction outcomes and committed offsets to identify records needing reprocessing.
6. Fix ID mapping before mass restarting.
7. Monitor producer fencing, transaction aborts, and group lag after remediation.

Do not immediately restart in a loop if two pods keep fencing each other. Restarting will not fix duplicate identity configuration.

## 8. AUTH: authentication or authorization errors

A consumer can stop because Kafka rejects authentication or authorization. Specific causes may include:

- Wrong or out-of-sync SASL username/password.
- Expired/unrefreshed OAuth token.
- Expired TLS certificate or misconfigured truststore.
- ACL disallowing reading the topic or joining the consumer group.
- Principal changed after a rollout.
- Broker policy or secret rotation changes.

In supported Spring Kafka versions, properties such as `authExceptionRetryInterval` on container properties can allow waiting and retrying certain authentication exceptions instead of stopping immediately. If the consumer stops due to such errors, reason `AUTH` helps observers classify it.

Do not just put a fast restart loop in place. Verify the root exception, credential source, ACLs, and broker logs. Until credentials are fixed, restarts only add noise, load, and rebalances.

### Handling AUTH

1. Correlate error time with secret/ACL/certificate changes.
2. Inspect the exact exception class.
3. Check consumer group/topic ACLs, not just bootstrap connectivity.
4. Verify the pod mounted the right secrets, certificates, and env variables.
5. If retryable, use finite intervals/backoffs per policy.
6. After fixing, confirm the consumer joins the group, polls, and offsets advance.

## 9. NO_OFFSET: no valid offset position

Kafka stores committed offsets per consumer group, topic, and partition. When a group has no valid committed offset yet, `auto.offset.reset` usually chooses `earliest` or `latest` if policy allows.

If configured with `auto.offset.reset=none`, the Kafka client can throw `NoOffsetForPartitionException` when no offset exists. Spring Kafka can stop the consumer and emit reason `NO_OFFSET`.

~~~yaml
spring:
  kafka:
    consumer:
      group-id: finance-reconciler
      enable-auto-commit: false
      auto-offset-reset: none
~~~

This setting fits when business logic **requires** an owner to confirm the starting point, yet can stop consumers when a new group or new partition lacks a committed offset.

### Handling NO_OFFSET

1. Identify affected group ID, topic, and partitions.
2. Check committed offsets and earliest/latest offsets still in the log.
3. Check whether group ID changed, partition count grew, or retention purged old data.
4. Obtain a business decision on starting at earliest/latest or seeding a specific offset.
5. Stop consumers cleanly before altering offsets to avoid colliding with active commits.
6. Assess replay/duplicate or data-skip risks before applying.
7. Restart and verify assignment and progress.

Do not automatically switch every `NO_OFFSET` to `latest`, as that can skip critical unprocessed records.

## 10. ERROR: abnormal consumer stop

`ERROR` is the catch-all error category. It appears when the consumer loop terminates due to an exception the container cannot continue handling. However, **a listener throwing an exception does not necessarily stop the consumer**.

For example, a transient listener failure:
- `DefaultErrorHandler` can retry within the same partition.
- After exhausting retries, the recoverer can publish to DLT.
- If recovery succeeds, the listener container can keep polling.
- In that case there may be no `ConsumerStoppedEvent(ERROR)`.

When `ERROR` occurs, find the root cause via stack traces, thread logs, and Kafka client state. Check serializers, deserializers, transaction managers, recoverers, broker connectivity, and exceptions outside the retry policy.

### Do not build auto-restart for every ERROR

A permanent data error or configuration error does not change across restarts. Continuous restarts cause rebalances, add lag, and mask root causes. Cap attempt counts, apply backoff, and escalate to alerts once thresholds are breached.

## 11. Rebalance does not mean consumer stopped

Rebalance describes **partition distribution** across members, whereas stop events describe **consumer lifecycle**.

For example, a group has two consumers A/B and four partitions. When consumer C joins, some partitions transfer from A/B to C. A and B may stay running; they receive partition revoked/assigned callbacks yet **do not necessarily** emit `ConsumerStoppedEvent`.

~~~text
Before scaling:
  Consumer A -> P0, P1
  Consumer B -> P2, P3

After scaling:
  Consumer A -> P0, P1
  Consumer B -> P2
  Consumer C -> P3

Rebalance occurred, yet A and B did not stop.
~~~

`onPartitionsAssigned`, `onPartitionsRevoked`, and `onPartitionsLost` manage partition ownership; do not use them as substitutes for `ConsumerStoppedEvent`.

With cooperative rebalancing, partitions can move incrementally; the number of revoke/assign callbacks does not equal the number of stop events either.

## 12. Concurrent containers: scoping events properly

Spring Kafka `ConcurrentMessageListenerContainer` creates multiple child containers per `concurrency`. Example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: inventory-service
      enable-auto-commit: false
    listener:
      concurrency: 4
      ack-mode: record
~~~

When the whole container stops, you may receive four `ConsumerStoppedEvent`s from the four child consumers. Event handlers must distinguish by listener/container and application instance.

Do not use a mere count of stop events as proof that all consumers finished, because:
- Events may fire multiple times across restarts.
- An async application event multicaster does not guarantee callback order.
- One child consumer may fail while the parent keeps running.
- Listener IDs or concurrency may change across deployments.

Use `ContainerStoppedEvent` and container status to confirm parent-level stop; use consumer group membership to know which Kafka members are actually active.

## 13. Designing a controlled restart strategy

An unexpected stop event usually needs remediation, yet **not always an immediate restart**.

~~~mermaid
flowchart TD
    A[ConsumerStoppedEvent] --> B[Classify reason]
    B --> C{Intentional shutdown?}
    C -->|Yes| D[Record expected stop]
    C -->|No| E{Self-recoverable?}
    E -->|No| F[Alert / fix config or offset]
    E -->|Yes| G[Check container lifecycle]
    G --> H[Apply backoff and retry budget]
    H --> I[Controller executes restart]
    I --> J[Verify started, assignment, and poll]
    J --> K{Stable?}
    K -->|Yes| L[End remediation]
    K -->|No| M[Escalation / prevent restart loop]
~~~

A restart controller should:
1. Maintain an **intentional shutdown flag** so it does not restart while the application is closing.
2. Identify the exact container/listener needing recovery.
3. Classify the reason; `AUTH`/`NO_OFFSET` usually require intervention first.
4. Only restart when the container is in a valid state, no longer stopping.
5. Ensure a single controller coordinates restarts for a given listener.
6. Limit attempt counts and use bounded backoff.
7. Confirm startup, assignment, polling, and advancing offsets after restart.
8. Coordinate with Kubernetes/systemd if the orchestrator also manages liveness/restarts.

### Anti-pattern

~~~java
@EventListener
public void handleStopped(ConsumerStoppedEvent event) {
    // Do not immediately restart the container on every event:
    // registry.getListenerContainer("ordersListener").start();
}
~~~

A synchronous handler calling `start()` while the container is still shutting down can cause races or a stop/start loop. If restart is needed, dispatch a signal to a controller outside the consumer thread and check lifecycle state before acting.

## 14. Offsets, acknowledgements, and redelivery when consumers stop

`ConsumerStoppedEvent` is not an offset commit barrier. A record may have updated the database successfully while its offset had not committed yet.

~~~text
Partition P0:
  offset 80: processed, committed offset 81
  offset 81: DB commit succeeded
  consumer stops before committing offset 82
  new member resumes from committed offset 81

Consequence: offset 81 may be reprocessed.
~~~

That is normal at-least-once behavior. Consumers need idempotency, such as `eventId` with a unique constraint/inbox inside the database transaction.

| Scenario | Risk | Mitigation |
|---|---|---|
| DB updated yet offset uncommitted | Record redelivered, duplicate side effect | Inbox/idempotency. |
| Acked early then listener fails | Offset may advance while business logic incomplete | Ack after processing. |
| Kafka transaction aborts on consumer stop | Outputs and offsets not committed as successful transaction | Properly wired transactional listener, `read_committed`. |
| Background worker still processing on consumer stop | Stale mutation may run after rebalance | Ownership token, cancellation, and idempotency. |
| DLT publish fails | Recovery not durable | Check send result, do not commit failed recovery. |

Do not manually reset offsets, `seekToEnd`, or commit a new offset merely because a stop event appeared. Offsets must be governed by business outcomes and approved policies.

## 15. Graceful shutdown with in-flight records

To shut down safely during rolling deployments:

1. Orchestrator requests the pod to terminate.
2. Application flags intentional shutdown state.
3. Container stops accepting new work per lifecycle.
4. Listener finishes or rolls back the in-progress record.
5. Offsets/transactions commit or abort per policy.
6. Consumer closes and emits `ConsumerStoppedEvent`.
7. Parent container reaches stopped state; `ContainerStoppedEvent` may follow.
8. Application context closes remaining resources.

Shutdown time must suffice for normal work, yet not be unbounded. If the listener offloads to a thread pool, stopping the container does not automatically ensure workers stopped. Separate shutdown protocols and in-flight work management are required.

Do not use an `@EventListener` for stop events to try finishing a batch or committing final offsets; that design easily runs on the wrong thread and clashes with lifecycle.

## 16. Transactional listeners and producer fencing

In Kafka consume–transform–produce flows, Spring Kafka can coordinate output records and input offsets in the same transaction. If the producer gets fenced, the old transaction is not allowed to commit validly; the consumer may stop and emit reason `FENCED`.

Verify:
- Is `transactionIdPrefix` unique per replica/factory?
- Does the listener container have the right Kafka transaction manager?
- Does `KafkaTemplate` participate in the container's transaction?
- Do downstream consumers set `isolation.level=read_committed` when needed?
- Do transaction timeout and `max.poll.interval.ms` fit processing duration?
- Do databases/HTTP endpoints have independent idempotency?
- Does post-rollback recovery use `AfterRollbackProcessor` per policy?

Producer fencing, consumer group zombie fencing, and static member `FencedInstanceIdException` are distinct mechanisms. Do not infer from a `FENCED` reason that every guarantee of the pipeline has been verified.

## 17. Testing ConsumerStoppedEvent in Spring tests

A test observer can collect events into a queue:

~~~java
@Component
public class ConsumerStopEventRecorder {

    private final BlockingQueue<ConsumerStoppedEvent> queue =
            new LinkedBlockingQueue<>();

    @EventListener
    public void record(ConsumerStoppedEvent event) {
        queue.offer(event);
    }

    public ConsumerStoppedEvent await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return queue.poll(timeout, unit);
    }
}
~~~

Imports can include `BlockingQueue`, `LinkedBlockingQueue`, and `TimeUnit`. This is a test example; production should not retain unbounded event objects holding references to sources/containers in a queue.

### Test scenarios

- **Normal stop:** start listener container, wait for consumer running, call stop, confirm event and container state.
- **Concurrency:** configure multiple child consumers, observe stop events per child without assuming strict ordering.
- **NO_OFFSET:** new group with `auto.offset.reset=none` and a partition missing committed offsets; verify version-specific behavior.
- **AUTH:** intentionally use rejected test credentials/ACLs; verify error classification and retry/stop policy.
- **FENCED:** use a Kafka test environment to create a controlled producer collision; never test on production clusters.
- **ERROR:** trigger a real error causing consumer stop per version; do not assume every listener exception triggers stop.
- **Shutdown intent:** ensure observers do not auto-restart containers stopping as planned.

Verify both container state and group assignments after the event; confirming the queue received the event alone does not prove recovery succeeded.

## 18. Monitoring and alerting

| Signal | Purpose | Proper interpretation |
|---|---|---|
| Stop event count by reason | Classify consumer stop counts | Event count, not current down count. |
| Start event count | Detect consumer restarts | Pair with stop count to spot loops. |
| Container running/stopped | Parent container state | Do not infer from one child event. |
| Consumer group member count | Currently active Kafka members | Detect capacity shortfall after stops. |
| Rebalance count/duration | Assignment stability | Do not equate with stop count. |
| Lag per partition | Backlog growing when members stop | Distinguish source traffic vs processing rate. |
| Committed offset | Starting point after restart | Correlate with in-flight work and retries. |
| Transaction abort/fencing | Diagnose `FENCED` reason | Cross-check prefix and rollouts. |
| Authentication failures | Diagnose `AUTH` | Credentials, ACLs, certificates. |
| No-offset errors | Diagnose `NO_OFFSET` | Reset policy, retention, group ID. |

Set alerts by severity: `NORMAL` during rollouts usually just needs logging; `AUTH` affecting the whole group may need paging; `NO_OFFSET` on critical flows needs owner review; repeated `FENCED` across valid replicas requires investigating transactional IDs; `ERROR` accompanied by rising lag/falling member count needs SLA response.

Logs should include instance ID, listener ID, group ID, timestamp, reason, relevant topic/partition when available, and exception class. Do not use high-cardinality event IDs/offsets or pod UIDs as metric labels; put them in logs/traces.

## 19. Runbook: Consumer stops unexpectedly

1. Record reason, timestamp, instance, listener/container ID, and group ID.
2. Determine whether a single child consumer or the entire container stopped.
3. Find the root exception prior to the event in logs.
4. Check group assignments, rebalances, broker health, and consumer lag.
5. Correlate committed offsets, in-flight work, and transaction outcomes.
6. Classify: `AUTH`, `NO_OFFSET`, `FENCED`, `ERROR`, or intentional stop.
7. Fix root cause or restart via a controller with backoff.
8. Confirm consumer started, received assignment, and resumed polling.
9. Verify duplicates/recovery and side effects outside Kafka.

Never reset offsets before knowing which record was last processed.

## 20. Runbook: Consumer continuously stops/starts

1. Build a timeline of started/stopped events per instance/listener.
2. Inspect repeated reasons and exception classes.
3. Cross-check deploy schedule, autoscaling, and liveness probes.
4. Check whether multiple restart controllers are controlling the same container.
5. For `FENCED`: fix identity collisions, not just retry counts.
6. For `AUTH`: fix credentials/ACLs.
7. For `NO_OFFSET`: establish an explicit offset policy.
8. For `ERROR`: inspect exceptions and stop/error handler policies.
9. Enable backoff, retry budgets, and escalation to prevent rebalance storms.
10. Monitor lag and membership after stabilizing.

## 21. Runbook: NORMAL yet consumer group lacks members

1. Correlate expected shutdown/deployment with `ConsumerStoppedEvent(NORMAL)`.
2. Check `ContainerStoppedEvent` and parent container state.
3. Count actual replicas/consumers against expected concurrency.
4. Check whether replacement pods started and joined the group.
5. Check whether partitions are still held or waiting on session timeout.
6. Check readiness, scheduler, deployment rollout, and startup failures.
7. Monitor lag per partition to see which workload lacks an active owner.

`NORMAL` is not a high-availability guarantee; it only means the consumer's stop branch was normal.

## 22. Runbook: FENCED during rolling deployment

1. Identify old/new processes and the overlap window.
2. Inspect actual `transactionIdPrefix` and `transactional.id`.
3. Distinguish valid fencing of an old producer from two independent pods sharing an ID.
4. Do not reuse fenced producers.
5. Check Kafka transaction aborts and source committed offsets.
6. Check outputs with a `read_committed` consumer and DB/API idempotency.
7. Fix identity/lifecycle before mass restarting.
8. Monitor fencing errors after rollout finishes.

## 23. Runbook: NO_OFFSET after increasing partitions

1. Identify new partitions and subscribed groups.
2. Check whether `auto.offset.reset` is `none`.
3. Check committed offsets and log start/end offsets.
4. Obtain business decision on earliest/latest or seeded offset.
5. Determine whether replaying/skipping backlog is permitted.
6. Apply change procedurally, avoiding concurrent consumer commits during reset.
7. Restart and verify assignment, polling, lag, and offsets.

## 24. ConsumerStoppedEvent control checklist

| Checkpoint | Question to answer | Operational evidence |
|---|---|---|
| Registration | Is `@EventListener` in the right Spring context? | Bean wiring and event logs. |
| Reason | Why did the consumer stop? | `getReason()`, stack traces. |
| Scope | Did one child or the whole parent container stop? | Concurrency, `ContainerStoppedEvent`. |
| Intent | Does the stop match a planned shutdown/deploy? | Rollout timeline, lifecycle flags. |
| Threading | Does the handler block consumer threads or call `KafkaConsumer` on the wrong thread? | Callback duration, executor policy. |
| Restart | Are there backoff, retry budget, and a single controller? | Restart state, attempts. |
| Membership | Were partitions reassigned and does the group have enough members? | Consumer group assignment. |
| Offset | Did the last record commit properly? | Committed offsets, AckMode. |
| Transaction | Was `FENCED` caused by producer collision or valid replacement? | Prefix, epoch, transaction logs. |
| Idempotency | Does redelivery cause business duplicates? | Event IDs, inbox/unique constraints. |
| Observability | Are stop/start, lag, and errors monitored properly? | Dashboards, alerts, runbooks. |

**Conclusion:** `ConsumerStoppedEvent` helps observe when a Spring Kafka consumer stops and provides `Reason` to classify normal shutdowns, errors, producer fencing, authentication failures, or missing offsets. It does not by itself certify that the entire container stopped, offsets committed, or business logic completed. A production solution must link events with container/group state, transactions/offsets, exception logs, and idempotency; keep event handlers lightweight and coordinate restarts carefully to avoid turning one incident into a rebalance loop.
