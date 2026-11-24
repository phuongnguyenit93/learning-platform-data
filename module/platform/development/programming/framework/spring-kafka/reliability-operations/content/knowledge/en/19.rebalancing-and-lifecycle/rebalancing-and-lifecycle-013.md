# Restarting container after error

## 1. Goal of container restart

In Spring Kafka, a **listener container** manages `KafkaConsumer`, the poll loop, consumer group membership, partition assignments, offset commits, and invocations of the `@KafkaListener` method. When a consumer encounters an error, there are cases where the container keeps running and self-recovers, yet also cases where it must stop.

**Restarting a container after an error** is the operation of restarting the lifecycle of a listener container that has stopped or is no longer operating properly, after identifying and fixing the root cause. Restarting is not synonymous with retrying a record; if the error lies only in a single business record, **DefaultErrorHandler**, BackOff, or DLT is usually the right handling path.

~~~text
KafkaListenerContainer
         |
         v
   KafkaConsumer.poll()
         |
    +----+--------------------+
    |                         |
Record received            Poll / lifecycle-layer error
    |                         |
    v                         v
@KafkaListener             Classify error
    |                         |
 +--+---------+         +-----+-----------------+
 |            |         |                       |
OK         Exception   Retryable             Cannot continue
 |            |         |                       |
 v            v         v                       v
Commit     Error       Kafka client /       Container STOPPED
per        handler     container retry             |
policy       |                                   v
          Retry /                            Fix root cause
          Recover                                 |
             |                                    v
             v                              Controlled restart
      Container continues                         |
                                                  v
                                           Join consumer group
                                                  |
                                                  v
                                           Receive new assignment
~~~

A sound operational policy must answer: which errors actually cause the container to stop, who is allowed to restart, when to restart, whether there is an attempt limit, and how to verify the consumer has resumed processing data.

## 2. Distinguishing KafkaConsumer and container types

| Component | Responsibility |
|---|---|
| KafkaConsumer | Kafka client performing subscribe, poll, commit, and group participation |
| KafkaMessageListenerContainer | Manages one consumer along with its consumer thread |
| ConcurrentMessageListenerContainer | Parent container managing multiple child containers |
| ConcurrentKafkaListenerContainerFactory | Creates containers from `@KafkaListener` endpoints |
| KafkaListenerEndpointRegistry | Finds and controls registered containers by listener ID |
| DefaultErrorHandler | Retries, seeks/redelivers, or recovers record errors per configuration |
| KafkaTransactionManager | Manages Kafka transactions in supported flows |
| Spring application events | Notifies consumer and container state/lifecycle |

Example of a listener with concurrency of three:

~~~text
ConcurrentMessageListenerContainer (parent)
         |
         +-- Child #0 --> KafkaConsumer #0
         +-- Child #1 --> KafkaConsumer #1
         +-- Child #2 --> KafkaConsumer #2
~~~

One child container can encounter an error and stop while other children continue operating. **A `ConsumerStoppedEvent` from one child does not by itself prove the parent stopped completely.** This matters if the application intends to auto-restart the entire endpoint from the event.

## 3. Basic lifecycle

~~~text
CREATED
   |
   | context startup / start()
   v
STARTING
   |
   | create consumer, subscribe, join group
   v
RUNNING
   |
   +--------------------------+
   |                          |
   | normal stop              | fatal error
   v                          v
STOPPING                   STOPPING / ERROR
   |                          |
   +-------------+------------+
                 |
                 v
              STOPPED
                 |
                 | start() once safe
                 v
              STARTING
                 |
                 v
              RUNNING
~~~

The diagram describes the conceptual lifecycle, not exact enum names in Spring Kafka. The **isRunning()** API reports container lifecycle state yet is insufficient to conclude the consumer is healthy.

A container can report **isRunning=true** while still:

- Not yet assigned partitions because the group is rebalancing.
- Paused.
- Disconnected from brokers and waiting to reconnect.
- Slow due to downstream or high consumer lag.
- Retrying an error through the error handler.

Conversely, **isRunning=false** does not specify whether an operator stopped it intentionally, the application is shutting down, or the container stopped due to an error.

## 4. Classifying errors before restarting

| Error category | Typical sign | Primary handling direction |
|---|---|---|
| Business exception | Listener failed to process record | DefaultErrorHandler, retry/DLT |
| Poison record | Same record fails repeatedly | Non-retryable classification or DLT |
| Deserialization failure | Cannot convert key/value bytes | ErrorHandlingDeserializer and error handler |
| Transient network | Broker disconnect, reconnect | Kafka client retry/reconnect; observe before restarting |
| Authentication failure | Wrong SASL credentials or TLS config | Fix secret/config, consider auth retry interval |
| Authorization failure | Missing READ on topic/group | Fix ACL; restart only once permissions are valid |
| Poll thread died | ConsumerStoppedEvent with error reason | Investigate cause, evaluate container restart |
| Failed to start | ConsumerFailedToStartEvent | Check executor, resources, and config |
| Producer fenced | ProducerFencedException in transactional listener | Check transactional ID, producer lifecycle |
| No offset | auto.offset.reset=none, group has no offset yet | Decide valid starting offset |
| Normal shutdown | Operator/context stopped container | Do not auto-restart |
| Container running yet paused | Consumer intentionally paused | Resume once conditions are met |

**Restart is a lifecycle-layer choice**, not the default handling action for every exception.

## 5. First handle record errors with an error handler

For record listeners, a common configuration is:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    var recoverer =
        new DeadLetterPublishingRecoverer(dltTemplate);

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );
}
~~~

The example uses `FixedBackOff` with a 1-second interval and three retries after the initial attempt. Once retries exhaust, the recoverer handles the record per policy.

Listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment"
)
public void consume(OrderCreated event) {
    fulfillmentService.processIdempotently(event);
}
~~~

If `fulfillmentService` hits a transient timeout, the handler can retry while the container stays running. If data permanently violates schema, it can recover to DLT.

### 5.1. Why doesn't restarting cure poison records?

~~~text
Consumer reads P0 offset 101
          |
          v
Record fails validation
          |
          v
Container is restarted
          |
          v
Consumer returns to offset 101 if uncommitted
          |
          v
Error record repeats
~~~

If the cause is the data itself, restarting usually just moves the error to the next poll. Rather than creating a restart loop, classify errors and provide a safe recovery path.

### 5.2. Stopping containers via error handler

Some Spring Kafka versions provide **CommonContainerStoppingErrorHandler** to stop the listener container when an error occurs. This is a fail-fast policy, not an automatic error-fixing mechanism.

If using a stopping error handler, clearly define when restarts are permitted, who controls restarts, and what happens to uncommitted records. Never stop and immediately start unconditionally, as the error will repeat.

## 6. Authentication and authorization: restart is not the first step

Kafka can reject clients due to invalid credentials or a principal lacking permissions on topics/groups. Example:

~~~text
Principal: User:order-consumer

Topic orders.created:
  READ required

Group order-fulfillment:
  READ required
~~~

If READ is missing on the group, restarting every few seconds does not create permissions. Update ACLs first.

### 6.1. authExceptionRetryInterval

Spring Kafka has the **setAuthExceptionRetryInterval(Duration)** API on `ContainerProperties` in supported versions. It allows waiting and retrying after certain `AuthenticationException` or `AuthorizationException` errors instead of stopping immediately per the corresponding default behavior.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setAuthExceptionRetryInterval(Duration.ofSeconds(30));

    return factory;
}
~~~

Check the API/version deployed to know which exceptions are retried and stop conditions.

Once ACLs are fixed on the broker for the right principal, the consumer may recover via retry/reconnect without needing a JVM restart, depending on actual state.

### 6.2. Secret rotation

If secrets are placed in environment variables at process startup, stopping and starting the Spring listener container alone **does not alter environment variables**.

After rotating credentials, check:

1. Has the secret source updated?
2. Does the application have a secret reload mechanism?
3. Does `ConsumerFactory` use the new credentials?
4. Does restarting the listener container create `KafkaConsumer` with the new config?
5. Must the whole pod/JVM be restarted?

Do not conclude a container restart succeeded merely because the `start` API returned normally.

## 7. Observing container stops via application events

Spring Kafka publishes lifecycle-related events. Useful events include:

| Event | Role |
|---|---|
| ConsumerStartingEvent | Consumer enters startup phase |
| ConsumerStartedEvent | Consumer has started |
| ConsumerStoppingEvent | Consumer is stopping |
| ConsumerStoppedEvent | Consumer stopped, with reason info in supported versions |
| ConsumerFailedToStartEvent | Consumer failed to start on time under corresponding conditions |
| ConsumerPartitionAssignedEvent | Consumer receives partitions |
| ConsumerPartitionRevokedEvent | Partitions revoked |
| ConsumerPartitionLostEvent | Consumer loses partition ownership |
| NonResponsiveConsumerEvent | Poll unresponsive within container monitoring window |

These events depend on framework lifecycle; an abruptly killed process may not have time to publish stop events.

Observer:

~~~java
@Component
public class KafkaConsumerLifecycleObserver {

    @EventListener
    public void stopped(ConsumerStoppedEvent event) {
        log.warn(
            "Kafka consumer stopped; reason={}, source={}",
            event.getReason(),
            event.getSource()
        );
    }

    @EventListener
    public void assigned(ConsumerPartitionAssignedEvent event) {
        log.info("Kafka partitions assigned: {}", event.getPartitions());
    }
}
~~~

Specific reason enum names differ across versions. Log the actual value rather than hardcoding a fixed set of causes if the API version is unverified.

### 7.1. Event observers are not restart controllers

An observer should only record metrics/logs and emit operational signals. **Do not call start() directly inside a ConsumerStoppedEvent handler** without checking parent state, stop reason, shutdown state, and backoff.

Events may arrive from the consumer thread or while stopping is still incomplete. If the multicaster runs asynchronously, callbacks may run on another thread. Lifecycle control must be coordinated separately.

## 8. ConsumerFailedToStartEvent

Failure to start may relate to:

- Task executor having no available threads.
- Saturated CPU or memory.
- Concurrent consumer count exceeding pod capacity.
- Misconfigured custom container factory.
- Context currently starting up/shutting down.
- Invalid bean dependencies or security configuration.

When **ConsumerFailedToStartEvent** appears, do not immediately restart dozens of times; if the cause is thread exhaustion, restarts only worsen resource starvation.

Inspect container and thread executor logs, concurrency sizing, JVM heap, GC, thread pools, and broker connection state.

## 9. Retrieving containers via KafkaListenerEndpointRegistry

Set an explicit ID on the listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment"
)
public void consume(OrderCreated event) {
    fulfillmentService.processIdempotently(event);
}
~~~

Use the registry to retrieve it:

~~~java
@Service
public class KafkaListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunning(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        return container != null && container.isRunning();
    }

    public void startIfStopped(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                "Unknown listener: " + listenerId
            );
        }

        if (!container.isRunning()) {
            container.start();
        }
    }
}
~~~

**Listener ID differs from group ID**. The registry looks up containers by `@KafkaListener(id=...)`, not Kafka `group.id`.

Additionally, containers created directly as Spring beans or via custom logic may not be registered in the registry the same way. For those containers, use the appropriate bean/reference lifecycle.

## 10. Restarting after the root cause is fixed

Safe operational procedure:

1. Record listener ID, container state, and stop reason.
2. Identify the root exception.
3. Distinguish intentional stops, application shutdown, and abnormal errors.
4. Fix the corresponding ACL, secret, serializer, broker, topic, or dependency.
5. Verify health of dependent components.
6. If the container is stopped, call `start` per lifecycle API.
7. If the container is still running yet needs a restart, stop and wait for completion before starting.
8. Monitor consumer group rebalance, assignments, and lag.
9. Confirm record processing actually resumes.

If the container is already stopped:

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orders-listener");

if (container == null) {
    throw new IllegalStateException("Listener is not registered");
}

if (!container.isRunning()) {
    container.start();
}
~~~

Do not embed offset-reset logic into default restarts. Restarting with existing committed offsets and resetting offsets are two distinct operational actions with different data impacts.

## 11. Stop-complete before start

A common bug is:

~~~java
container.stop();
container.start();
~~~

Two consecutive calls do not guarantee consumer threads finished stopping if stop runs asynchronously. A container still in stopping state may not accept `start` as intended.

Spring Lifecycle supports **stop(Runnable)** to receive a callback after stop completes.

Example for Spring Framework 6 / Java 17 with `TaskScheduler`:

~~~java
@Service
public class KafkaRestartService {

    private final KafkaListenerEndpointRegistry registry;
    private final TaskScheduler scheduler;

    public KafkaRestartService(
            KafkaListenerEndpointRegistry registry,
            TaskScheduler scheduler) {

        this.registry = registry;
        this.scheduler = scheduler;
    }

    public void restart(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                "Unknown listener: " + listenerId
            );
        }

        Runnable scheduleStart = () ->
            scheduler.schedule(
                () -> {
                    if (!container.isRunning()) {
                        container.start();
                    }
                },
                Instant.now().plusSeconds(5)
            );

        if (container.isRunning()) {
            container.stop(scheduleStart);
        }
        else {
            scheduleStart.run();
        }
    }
}
~~~

Conditions of the example:

- `TaskScheduler` is an initialized Spring-managed bean.
- The `schedule` API accepts `Instant` in Spring Framework 6; older versions may accept `Date`.
- Code needs corresponding imports.
- Caller must have operational authority.
- Do not run restart while the application context is shutting down.
- In production, prevent multiple concurrent restart requests.

The stop callback only **schedules** the start operation; start itself runs on the scheduler thread, not directly while the consumer thread is exiting.

### 11.1. Guarding against concurrent restarts

If two operator requests or two event callbacks simultaneously request a restart, a race between stop and start can occur. Keep dedicated state per listener ID:

~~~text
restartRequested
        |
        v
Check restartInProgress?
   /                \
 YES                 NO
  |                   |
  v                   v
ignore/log        mark in progress
                      |
                      v
              stop until complete
                      |
                      v
                  schedule start
                      |
                      v
                  clear state
~~~

This can be implemented with `ConcurrentHashMap` and `AtomicBoolean`, plus a state machine for **STOPPING**, **WAITING_TO_RESTART**, **STARTING**, and **RUNNING**. When start fails, release the guard or transition to a retry state rather than leaving `restartInProgress` stuck forever.

## 12. Avoid auto-restarting directly inside ConsumerStoppedEvent

The following code is unsafe as a general policy:

~~~java
@EventListener
public void stopped(ConsumerStoppedEvent event) {
    registry.getListenerContainer("orders-listener").start();
}
~~~

Problems:

- Can fire during a normal container stop.
- Event may come from a child container inside a parent concurrent container.
- Consumer thread or parent may still be stopping.
- Application context may be shutting down.
- Root cause still persists, leading to a restart loop.
- No backoff or restart budget.
- No verification of assignment or processing after starting.

If auto-restart is needed, the event listener should only record the cause and submit a request to a **restart coordinator** running on a separate executor/scheduler.

### 12.1. One stopped child does not mean the entire endpoint stopped

~~~text
ConcurrentMessageListenerContainer
   |
   +-- child #0 RUNNING
   +-- child #1 STOPPED (error)
   +-- child #2 RUNNING
~~~

The parent may still report `isRunning=true`. Calling `parent.start()` does not necessarily restore the failed child as expected.

Policy decisions needed:

- Accept temporarily reduced capacity and alert.
- Stop the entire endpoint then restart after stop-complete.
- Perform targeted recovery per supported API/version.
- Let the orchestrator restart the pod when a single child cannot recover safely.

Do not rely on a single child event to start the parent unconditionally.

## 13. Backoff, jitter, and restart budgets

Continuous rapid restarts can cause:

- Connection/SASL/TLS handshake storms.
- Continuous rebalancing.
- Rising consumer lag.
- Extra load on the broker group coordinator.
- Log noise obscuring the root error.
- Multiple pods restarting simultaneously causing a thundering herd.

Simple policy:

~~~text
Attempt 1: 5 seconds
Attempt 2: 10 seconds
Attempt 3: 20 seconds
Attempt 4: 40 seconds
Attempt 5: 60 seconds (cap)
~~~

Add small jitter so instances do not run in lockstep.

~~~text
delay(attempt) =
   min(maxDelay, baseDelay * 2^(attempt - 1))
   + randomJitter
~~~

Cap attempts within a time window or open a circuit after consecutive failures. Once the budget is exceeded, alert and require operator intervention.

Do not infinitely auto-restart unrecoverable errors like bad ACLs, wrong passwords, missing topics under disallowing configs, broken serialization configs, or transactional ID collisions.

## 14. Do not restart during application shutdown

When the Spring context is closing, containers are stopped per lifecycle. **ConsumerStoppedEvent** is normal during this process.

If auto-restarting a listener from that event, the pod may fail to shut down on time or the scheduler may try to create new consumers after dependencies are already destroyed.

A restart coordinator should maintain a shutdown status flag set from **ContextClosedEvent**, or check application lifecycle status before running scheduled restarts.

Conceptual example:

~~~java
private volatile boolean shuttingDown;

@EventListener
public void contextClosed(ContextClosedEvent event) {
    shuttingDown = true;
}

public void restartIfAllowed(MessageListenerContainer container) {
    if (shuttingDown) {
        return;
    }

    // Apply reason, backoff, budget, and stop-complete.
}
~~~

This is only partial protection; production must also cancel scheduled tasks and release the scheduler when the context closes.

## 15. Listener restart and pod restart are two different levels

| Recovery | Impact |
|---|---|
| Spring container stop/start | Recreates consumer lifecycle inside the same JVM |
| Application process restart | Reinitializes entire Spring context, beans, and client factories |
| Kubernetes pod restart | Replaces process/container, can pick up new env vars or mounted secrets depending on setup |
| Pause/resume | Pauses consumption while typically keeping group membership |
| Record retry | Keeps listener container active and handles specific data errors |

Pod restarts can solve cases where configs/secrets are only loaded at JVM start. Yet they also incur larger cold starts, warm-ups, and rebalances than restarting just the listener.

### 15.1. Liveness and readiness

Do not fail liveness merely because Kafka temporarily lost connectivity if that triggers a pod restart storm. Represent degraded broker or consumer states via appropriate readiness/health details.

For Kafka-consumer-only services, Kubernetes readiness does not replace Kafka group assignment. Regardless of whether the pod is ready, membership is still governed by consumer polling/heartbeats and the group coordinator.

## 16. Rebalancing after restart

When a consumer leaves the group, its partitions can be reassigned. When the container starts, the new consumer joins the group and Kafka may rebalance again.

~~~text
Before:
  Consumer A -> P0, P1
  Consumer B -> P2, P3

Stop A:
  Consumer B may receive P0, P1, P2, P3

Start A:
  Group rebalances
  Consumer A -> P0, P1
  Consumer B -> P2, P3
~~~

This is only an illustrative diagram; actual assignment depends on the assignor and membership. With cooperative rebalancing, partitions can migrate incrementally.

**Continuous restarts can cause continuous rebalances**, lowering throughput even while many consumers stay alive. Therefore, after restarting, measure:

- Rebalance count/duration.
- Partition assignment events.
- Consumer lag per partition.
- Throughput and processing latency.
- Number of restart attempts.

## 17. Offset commits and record redelivery

Kafka groups store the next offset to read for each partition. If a listener processed a record yet its offset had not committed when the container stopped, the record can be redelivered after restart.

Example:

~~~text
Committed offset: 100

Consumer A:
  offset 100 -> business side effect OK
  offset 101 -> business side effect OK
  offset 102 -> error
  crashes before commit

Consumer after restart:
  re-reads from offset 100
~~~

This is a characteristic of at-least-once delivery. Restarts do not guarantee exactly-once for database/HTTP side effects.

### 17.1. Idempotency

For Order Fulfillment workflows, each event should have a stable event ID. A `processed_event` table can use a unique constraint:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Within the same DB transaction, record the event marker and business mutation. When an event is redelivered, the unique constraint detects the duplicate and prevents a second side effect.

Merely checking **existsById** before inserting is insufficient due to race conditions. Real DB unique constraints and transactions are the essential protection layer.

### 17.2. Graceful shutdown

A controlled stop gives the container a chance to finish processing and commit per `AckMode`. However, if a listener is blocked or the pod is killed before the deadline, records may still need redelivery.

Balance stop timeout, processing p95/p99, retry duration, transaction timeout, and Kubernetes termination grace period.

## 18. Transactional listeners and ProducerFencedException

In consume-transform-produce, listeners can write Kafka outputs via `KafkaTemplate` and include input offsets in the same transaction. If the transaction aborts, uncommitted outputs are invisible to `read_committed` consumers and input offsets do not commit in that transaction.

When the container restarts, input records can be redelivered. This aligns with Kafka transaction semantics.

However, when a producer is **fenced** due to a duplicate transactional ID:

- The old producer cannot continue normal transactions.
- Find which instance generates the same transactional ID.
- Check transaction ID prefixes across pods.
- Let Kafka transaction manager/producer factory manage lifecycle.
- Do not infinitely retry the same fenced producer.

If an error occurs in a record while a transactional listener is processing, Spring Kafka can use **AfterRollbackProcessor** to retry or recover after transaction rollback. No need to restart the whole container for every transaction abort.

## 19. Pause/resume differs from stop/start

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orders-listener");

if (container != null) {
    container.pause();
}
~~~

When conditions recover:

~~~java
if (container != null) {
    container.resume();
}
~~~

| Operation | Typical impact |
|---|---|
| pause | Temporarily pauses receiving/processing records per container API, still keeps group membership if polling fits |
| resume | Resumes consumption |
| stop | Stops consumer/container, may leave group |
| start | Reinitializes consumer and joins group |
| Pod restart | Restarts entire process/JVM |

For brief downstream maintenance, pause/resume can avoid more rebalances than stop/start. Yet pause does not revive a dead poll thread.

Do not leave containers paused too long without monitoring; consumer lag will grow and event freshness may violate SLOs.

## 20. autoStartup and controlled startup

Spring Kafka allows listeners not to start automatically when the context initializes:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    autoStartup = "false"
)
public void consume(OrderCreated event) {
    fulfillmentService.processIdempotently(event);
}
~~~

Once dependencies are ready:

~~~java
registry.getListenerContainer("orders-listener").start();
~~~

**autoStartup=false is not an auto-restart-after-error mechanism.** It only decides at application startup whether to start the listener automatically.

This is useful when needing state warm-up, access policy checks, or waiting on external dependencies before letting Kafka consumers receive records.

## 21. Missing committed offset errors

If a consumer group has no committed offset yet and **auto.offset.reset=none**, the Kafka client may fail to determine a valid starting position.

In that case, do not restart endlessly. Choose an offset policy:

- **earliest** if backlog must be processed from the start.
- **latest** if business logic allows reading only new data.
- An operator-chosen offset under a replay procedure.
- Initializing the consumer group once an appropriate checkpoint exists.

Changing offsets affects business data, unlike restarting a container. Do not pick `latest` just to make the error vanish if old backlog still needs processing.

## 22. Monitoring and alerts

| Metric / signal | Purpose |
|---|---|
| Container isRunning | Determine lifecycle status |
| ConsumerStoppedEvent reason | Find why the container stopped |
| ConsumerFailedToStartEvent | Detect startup failures |
| Restart attempt count | Detect restart loops |
| Time since last successful poll | Detect consumers making no progress |
| Partition assignment | Confirm group join after start |
| Rebalance rate/duration | Measure impact of restarts |
| Consumer lag per partition | Measure backlog after restart |
| Listener processing duration | Find slow batch/record processing |
| Commit failures | Evaluate offset progression |
| Authentication/authorization errors | Distinguish credential errors from ACLs |
| Producer fencing | Detect transactional ID collisions |
| DLT publish failures | Detect failed recovery |
| Pod restarts/OOM/GC | Find resource root causes |

A useful lifecycle log:

~~~text
timestamp=2026-11-15T10:21:34Z
service=order-fulfillment
listenerId=orders-listener
groupId=order-fulfillment
event=consumer_stopped
reason=ERROR
restartAttempt=2
scheduledDelaySeconds=10
action=restart_pending
~~~

Do not log JAAS passwords, tokens, private keys, or raw payloads. Monitoring container stopped alongside lag and partition assignment helps prevent false alerts when topics simply have no data.

### 22.1. Verifying recovery

After calling `start()`, verify:

1. Container transitions to running.
2. Consumer is created and group membership stabilizes.
3. Partition assignment appears.
4. Listener processes valid events.
5. Offset commits advance per policy.
6. Consumer lag decreases if the topic has backlog.
7. No further authentication, fencing, or restart loop errors occur.
8. DLT/retries continue functioning.

**`start()` returning without throwing an exception does not prove all of the above succeeded.**

## 23. Integration tests for restarts

Embedded Kafka or Testcontainers can be used to test lifecycle against a real broker.

### 23.1. Stop/start test

1. Start a listener with a fixed ID.
2. Retrieve the container via `KafkaListenerEndpointRegistry`.
3. Stop the container and await the stop callback.
4. Confirm stopped state.
5. Call `start` via a scheduler/management thread.
6. Await partition assignment.
7. Publish a new record and confirm the listener processes it.

### 23.2. Rebalance test

1. Start two consumers in the same group.
2. Record initial assignments.
3. Stop one consumer.
4. Wait for the remaining consumer to receive partitions.
5. Start the stopped consumer again.
6. Confirm new assignments and that no two consumers own the same partition in the same group in a valid assignment state.
7. Check lag and processing.

### 23.3. Crash-before-commit test

1. Send an event with a stable ID.
2. Have the consumer create a DB side effect yet crash before Kafka offset commit.
3. Restart the consumer.
4. Observe the record may be redelivered.
5. Confirm DB unique constraint/idempotency blocks duplicate side effects.

### 23.4. Non-self-recoverable error test

1. Configure invalid ACLs or credentials in a test environment.
2. Confirm the restart coordinator does not loop infinitely.
3. Fix permissions or secrets.
4. Restart only once conditions are met.
5. Confirm group and record processing recover.

### 23.5. Shutdown test

When the context closes, stopped events must not trigger new restarts. The scheduler must cancel or ignore pending scheduled tasks and the process completes graceful shutdown.

## 24. Practical example: Order Fulfillment after ACL error

Suppose Order Fulfillment runs two child consumers with group **order-fulfillment** reading topic **orders.created**. An ACL change causes the application principal to lose READ permission on the group.

Symptoms:

~~~text
GroupAuthorizationException
Consumer stopped or auth retry scheduled
Listener no longer processes records
Consumer lag increases
~~~

Workflow:

1. Read the root exception and identify the actual group ID.
2. Check principal and READ ACLs on topic/group.
3. Check `ConsumerStoppedEvent` and parent container status.
4. Check whether `authExceptionRetryInterval` is configured.
5. Fix ACLs through Kafka administration procedures.
6. If the consumer is retrying, observe whether it recovers without restarting.
7. If the container already stopped, perform a controlled restart.
8. Wait for group rebalance and partition assignment.
9. Confirm lag drops and committed offsets advance.
10. Check duplicate detection because uncommitted records may be redelivered.

In this situation, **fixing the ACL is what enables recovery**. Restarting merely reactivates the stopped consumer's lifecycle; it does not grant access rights.

## 25. Production runbook

1. Identify listener ID, topic, group ID, pod, and concurrency.
2. Record time/reason of stopped events and root exceptions.
3. Inspect parent and child container states.
4. Distinguish intentional stop/shutdown from abnormal errors.
5. For record failures, prefer error handler and DLT.
6. For broker outages, check whether the Kafka client auto-reconnects.
7. For ACLs/secrets, fix security configuration first.
8. For producer fencing, inspect the transactional ID namespace.
9. For resource exhaustion, restore executor/CPU/memory.
10. If restart is necessary, use the registry or managed container bean.
11. Coordinate stop-complete before start.
12. Block concurrent requests, apply backoff, and enforce a restart budget.
13. Do not auto-restart during context shutdown.
14. Wait for the consumer to join the group and receive assignments.
15. Monitor rebalance, consumer lag, commits, retry/DLT, and throughput.
16. Verify idempotency of side effects that might replay.
17. Document root cause, remediation, and recovery evidence.

## 26. Common mistakes

**Every listener exception needs a restart.** False; record errors are normally handled by `DefaultErrorHandler` or recovery policies.

**Container isRunning=true suffices to say healthy.** False; the consumer may not have partitions yet, may be paused, or may still be retrying infrastructure errors.

**One ConsumerStoppedEvent means the entire concurrent parent stopped.** Not certain; the event may come from a single child.

**Calling start() immediately inside a stopped event is safe.** Can race with the consumer thread and stop lifecycle.

**Consecutive stop then start always equals a successful restart.** Always wait for stop-complete.

**Infinite restarts will fix an ACL error.** No; permissions or credentials must be fixed.

**Restarting the listener container reloads all secrets.** Not if secrets are loaded into environment variables at JVM startup.

**Restarts never cause duplicates.** False; processed-but-uncommitted records can be redelivered.

**Pause equals stop.** No; pause usually retains group membership.

**ProducerFencedException is just a network timeout.** No; the old producer is no longer valid for that transactional identity.

**Increasing concurrency cures consumers failing to start.** Can worsen thread/resource exhaustion.

**start() not throwing an exception means the incident is over.** You must verify assignment, offsets, throughput, and lag.

## 27. Takeaways

**Restarting a container after an error** in Spring Kafka is the operation of restoring listener lifecycle when a container has stopped or can no longer continue consuming safely. It differs from retrying records. `DefaultErrorHandler`, DLT, and `AfterRollbackProcessor` typically handle consumption-time errors without restarting the container.

When a restart is needed, use `KafkaListenerEndpointRegistry` or Spring-managed container references, confirm the root cause is resolved, coordinate stop-complete before start, and avoid operating directly inside consumer lifecycle events. Auto-restarts need backoff, jitter, a restart budget, and blocking during application shutdown.

Restarts can cause consumers to leave and rejoin the group, triggering rebalances and replaying uncommitted records. Combine lifecycle monitoring, partition assignments, policy-based offset commits, idempotent side effects, and consumer lag checks to ensure the system truly recovers rather than endlessly restarting.
