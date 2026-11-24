# Designing Behavior for Service Restarts

A Kafka-consuming service must resume processing accurately after a process stops, a pod is replaced, or a server reboots. Achieving this requires designing consumer groups, committed offsets, record acknowledgment timing, listener shutdown behavior, and how potentially redelivered events are handled.

When a service restarts with the same `group.id`, the Kafka consumer resumes from each partition's most recently committed offset, provided that offset is still valid. Records that finished processing before their offset was committed can be redelivered. Consequently, the service must tolerate duplicate processing, especially when writing to a database or calling external systems prior to committing offsets.

Recovery behavior does not come from a single setting. It is the combined result of the Kafka consumer group, Spring Kafka listener container, `AckMode`, error handler, application lifecycle, and business-logic idempotency.

## 1. What Must a Service Restart Guarantee?

When a service stops and starts again, the design should achieve these goals:

- Resume reading from the consumer group's committed progress.
- Never skip events that were not successfully processed.
- Tolerate events being redelivered after failures or restarts.
- Stop consumers gracefully to minimize mid-flight interrupted records.
- Resume retries and dead-letter handling per the chosen policy.
- Provide logs, metrics, and audit trails sufficient to know where the service stopped and where it resumed.

Kafka retains records in topics according to retention policies. Consumer groups store committed offsets to track the next read position. Restarting a service neither clears topics nor resets offsets back to the beginning of a topic automatically.

## 2. Same Group ID Resumes from the Committed Offset

Kafka stores offsets per consumer group and partition pair. When a consumer starts, it joins the group using `group.id`. After receiving partition assignments, the consumer uses the group's committed offsets to resume reading.

For example, suppose group `billing-service` has committed partition 0 up to offset 125:

```text
Topic: orders.events
Group: billing-service

Partition 0
  Offset 120 ... 124: already processed and committed
  Offset 125: next position to read
  Offset 126 ...: subsequent records
```

If the process restarts and the committed offset remains valid, the consumer resumes from offset 125. Under normal operation, it does not re-read records prior to that position.

Key requirements:

- Keep `group.id` stable across deployments and restarts to continue from the same progress.
- Never delete or reset group offsets during routine deployment workflows.
- Ensure committed offsets stay within the partition's still-retained log range.
- Let the Spring Kafka container manage the consumer lifecycle and offset commits according to the selected `AckMode`.

If every restart generates a new group ID, Kafka treats it as a brand-new consumer group. A new group has no prior committed offsets and applies `auto.offset.reset`.

## 3. Configuring the Consumer for Recoverability

Example configuration for an order-event processing service:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.trusted.packages]": com.example.messaging.event
        "[spring.json.value.default.type]": com.example.messaging.event.OrderCreated
    listener:
      ack-mode: record
```

Meaning:

- `group-id` must remain stable across restarts so the group reuses committed offsets.
- `enable-auto-commit: false` lets the Spring Kafka container control commit timing.
- `ack-mode: record` commits after each record listener processes a record successfully.
- `auto-offset-reset: earliest` only takes effect when the group has no valid offset for a partition; it does not overwrite valid committed offsets.

`earliest` is an illustrative choice, not mandatory for every service. Some business flows may need `latest` or another policy depending on how new groups initialize. Choose based on data requirements and replay needs.

## 4. auto.offset.reset Is Not a Rewind-on-Restart Command

`auto.offset.reset` decides where a consumer starts when no valid committed offset is found for a partition. It does not determine read positions on every service restart while the group still holds valid offsets.

| Value | Behavior When No Valid Offset Exists |
| --- | --- |
| `earliest` | Starts from the earliest offset still retained in the partition |
| `latest` | Starts at the end of the log and consumes only newly written records |
| `none` | Throws an error because no valid offset exists |

Examples:

- Service restarts while group has committed offsets: resumes from the committed offset; `earliest` does not make it re-read from the start.
- Service uses a new group ID: no offsets exist yet; `earliest` reads from the oldest retained record, while `latest` starts at the log tail.
- Group offsets expired or fell outside retained log bounds: consumer applies the corresponding reset policy.

Therefore, changing `auto-offset-reset` from `latest` to `earliest` is not a safe way to replay an active group. To replay intentionally, use a new group or reset offsets through a controlled operational procedure.

## 5. Offsets Can Expire While a Service Is Down

Committed offsets are stored in the internal `__consumer_offsets` topic. Brokers retain offsets for inactive groups for a configured period, typically governed by `offsets.retention.minutes` on the broker (exact configuration and behavior depend on the Kafka version).

If a service stays down longer than the offset retention window, the group may lose its committed offsets by the time it returns. `auto.offset.reset` then kicks in. With `latest`, the service may skip older records still in the topic; with `earliest`, it may reprocess large amounts of retained data.

For services that may experience extended downtime:

- Know the Kafka cluster's offset retention configuration.
- Alert when a consumer group stays inactive too long.
- Inspect committed offsets before restarting after prolonged downtime.
- Maintain replay/reconciliation procedures in case offsets are gone.
- Evaluate topic retention to ensure data needed for recovery still exists.

Offset retention and topic retention are separate policies. A group can lose its offsets while records still exist; conversely, offsets may exist while records at those positions have already been purged by topic retention, rendering the offsets out of range.

## 6. Restarts Can Cause Redelivery

The decisive factor is the relationship between business side effects and offset commits.

### 6.1. Restart Before Processing Finishes

```text
Consumer receives offset 125
        |
        v
Processing business logic
        |
        X  Process is killed
        |
        v
Offset 125 not yet committed
        |
        v
Service restarts
        |
        v
Consumer receives offset 125 again
```

Uncommitted records can be redelivered to the consumer group after the group recovers and partitions are assigned. This behavior is necessary to avoid skipping unfinished records.

### 6.2. Business Logic Succeeds, Process Stops Before Commit

```text
Consumer receives offset 125
        |
        v
Database transaction commits successfully
        |
        X  Process is killed before Kafka offset commit
        |
        v
Offset 125 still uncommitted
        |
        v
Restart -> record 125 is redelivered
```

The database already reflects the change, yet Kafka does not know the consumer finished the record. A second execution can duplicate side effects if the service is not idempotent.

### 6.3. Commit Before Business Logic Finishes

```text
Consumer receives offset 125
        |
        v
Commit next offset: 126
        |
        X  Process is killed before updating database
        |
        v
Restart -> consumer starts from 126
```

In this scenario, record 125 may never be redelivered even though business work never finished. This risks losing business effects due to premature commits.

For consumers interacting with databases or HTTP APIs, generally complete side effects first and acknowledge offsets afterward, while making side effects idempotent to withstand redelivery.

## 7. How AckMode Affects Post-Restart Behavior

Spring Kafka `AckMode` controls when the container commits offsets:

| AckMode | Commit Boundary | Observable Post-Restart Behavior |
| --- | --- | --- |
| `RECORD` | After each record listener processes a record successfully | Committed records are unlikely to be re-read; uncommitted ones can be redelivered |
| `BATCH` | After successfully processing all records from one poll | Records already processed in an uncommitted batch can be redelivered |
| `TIME` / `COUNT` / `COUNT_TIME` | By time or count threshold at container safe points | A group of records since the last commit can be redelivered |
| `MANUAL` | Listener calls `acknowledge()`, container batches commits per manual semantics | Uncommitted records can be redelivered |
| `MANUAL_IMMEDIATE` | Ack on the consumer thread triggers immediate commit | Commit window may be narrower, yet redelivery remains possible if the process dies before the broker persists the commit |

`RECORD` is straightforward when you want commits tightly coupled to each record. `BATCH` reduces commit overhead at the cost of a wider replay window after a crash. Manual modes help when the listener must guard acknowledgment conditions, provided `acknowledge()` is called after the business boundary.

No `AckMode` by itself creates an atomic transaction spanning Kafka offsets and a regular database transaction.

## 8. Writing a Listener That Tolerates Restarts and Redelivery

Example listener delegating event processing to a transactional database service:

```java
package com.example.billing.consumer;

import com.example.messaging.event.OrderCreated;
import com.example.billing.service.BillingService;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final BillingService billingService;

    public OrderCreatedListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
            id = "billingOrdersListener",
            topics = "orders.events",
            groupId = "billing-service"
    )
    public void onOrderCreated(OrderCreated event) {
        billingService.processIdempotently(event);
    }
}
```

With `AckMode.RECORD`, the container commits the offset after the method returns normally. If `processIdempotently` throws an exception, the container delegates to the error handler; the offset is not committed as a normal successful record.

The key lies inside `processIdempotently`: the service must recognize a previously processed `eventId` and avoid re-applying side effects.

## 9. Idempotency Protects Side Effects on Redelivery

A common pattern stores `eventId` in an inbox table with a unique constraint inside the same database transaction as business updates.

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Service executing within a single transaction:

```java
@Transactional
public void processIdempotently(OrderCreated event) {
    boolean inserted = processedEventRepository.insertIfAbsent(
            event.eventId(), Instant.now()
    );

    if (!inserted) {
        // Event was already applied in a previous transaction.
        return;
    }

    billingRepository.createInvoice(event.orderId(), event.total());
}
```

`insertIfAbsent` must use an atomic database operation, such as `INSERT ... ON CONFLICT DO NOTHING` in PostgreSQL or an equivalent unique-constraint mechanism. Never use an unlocked "query then insert" check, as two concurrent consumers/processes can both observe the event as absent.

If the database transaction rolls back, both the inbox row and invoice update roll back together. If the transaction commits successfully before the Kafka offset commits, the event may be redelivered; next time, the unique constraint detects the already-processed event and the listener returns successfully so the container commits the offset.

Idempotency should rely on a stable producer-generated event ID. Do not use a lone Kafka offset as the idempotency key if events may be replayed to another topic/partition or republished with new offsets.

## 10. Graceful Shutdown Before Process Termination

Services regularly stop due to deployment rollouts, scale-ins, maintenance, or host shutdowns. Controlled shutdown reduces the number of listener invocations cut off mid-flight.

Spring Kafka listener containers are managed by Spring's lifecycle. When the application context closes cleanly, Spring stops beans in lifecycle order; the container stops consumers and releases resources. Allocate sufficient shutdown time so active listeners can finish in-flight work.

Example Spring Boot shutdown timeout configuration across lifecycle phases:

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
```

In containerized environments, Kubernetes `terminationGracePeriodSeconds` must be long enough to accommodate application shutdown and active listeners. If the orchestrator sends SIGKILL before the application finishes, graceful shutdown cannot complete.

Spring Boot's `server.shutdown: graceful` governs graceful shutdown of the embedded web server. It does not replace the Kafka listener container's lifecycle shutdown. Kafka listeners are managed by the Spring context and must be governed via appropriate lifecycle/timeout settings.

### 10.1. Intentionally Stopping a Listener

You can manage listener containers via `KafkaListenerEndpointRegistry` when pausing event consumption before maintenance:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class KafkaListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("billingOrdersListener");
        if (container != null) {
            container.stop();
        }
    }
}
```

The ID passed to `getListenerContainer` must match the `@KafkaListener`'s `id`. Calling `stop()` asks the container to stop via its lifecycle; never close a Spring-managed Kafka consumer directly. If you need to wait synchronously during a maintenance workflow, await the shutdown callback/completion using your Spring Kafka version's API.

### 10.2. Do Not Close Resources Before Listeners Stop

If listeners depend on database connection pools, HTTP clients, or application-managed executors, those resources must stay available while listeners stop and finish in-flight work. Order lifecycle/shutdown phases so listeners stop before closing dependencies they require.

Never use `@PreDestroy` to manually invoke `consumer.close()` on consumers managed by a Spring Kafka container. The container owns creating, polling, committing, stopping, and closing the consumer.

## 11. Readiness and Liveness on Startup

In Kubernetes or other orchestrators, distinguish between:

- **Liveness:** the process is alive and not deadlocked to the point of needing a restart.
- **Readiness:** the instance is ready to accept traffic or work per application criteria.
- **Kafka listener startup:** the listener container has started and joined the consumer group.

A process may open its HTTP port before its Kafka listener receives partition assignments. If a service is only ready once listeners join the group, reflect container/group assignment state in a readiness indicator. Avoid reporting readiness solely because the JVM started.

If you need to wait for dependencies before listeners consume events, set `autoStartup=false` on the listener and start the container once dependencies are ready:

```java
@KafkaListener(
        id = "billingOrdersListener",
        topics = "orders.events",
        groupId = "billing-service",
        autoStartup = "false"
)
public void onOrderCreated(OrderCreated event) {
    billingService.processIdempotently(event);
}
```

Once startup conditions are met, retrieve the container from `KafkaListenerEndpointRegistry` and call `start()`. Prevent listeners from consuming records before database migrations, caches, or critical dependencies are ready.

## 12. Rebalances When Services Restart or Scale

When a consumer leaves a group, Kafka redistributes partitions across remaining members. Restarting a pod typically triggers membership changes and a rebalance. When the new instance starts, it joins the group and can shift assignments again.

During a rebalance:

- Consumers may pause receiving records while the group synchronizes assignments.
- Partitions are revoked from old members and assigned to new members.
- Uncommitted records can be re-read once new assignments settle.
- Consumer lag may rise temporarily.

To minimize disruption:

- Use rolling deployments with controlled instance turnover.
- Avoid restarting all replicas simultaneously unless necessary.
- Monitor rebalance counts/durations and consumer lag.
- Consider the cooperative sticky assignor where supported by cluster/client versions to reduce partition movement.
- Keep listener execution within poll intervals and design idempotently.

Do not try to suppress every rebalance by forcing consumers to stay alive indefinitely. Rebalancing is the normal mechanism for recovering and redistributing partitions when membership changes.

## 13. Static Membership and group.instance.id

Kafka supports static membership via `group.instance.id`. Static members can reduce rebalances during brief restarts because the broker waits for the member to return instead of immediately reassigning partitions.

Consumer client configuration example:

```yaml
spring:
  kafka:
    consumer:
      properties:
        group.instance.id: ${KAFKA_GROUP_INSTANCE_ID}
```

`group.instance.id` must remain stable for the same instance across restarts and be unique across concurrent consumers in the group. Never assign the same static ID to all pods; duplicate IDs can cause fencing or prevent instances from coexisting properly.

If a listener uses concurrency greater than one, ensure each Kafka consumer's static member ID is genuinely unique. How Spring Kafka constructs/suffixes child consumer IDs can depend on version and configuration; verify your version's behavior before enabling static membership.

Static membership does not replace committed offsets, graceful shutdown, or idempotency. It only changes how the group handles temporarily departing members; if an instance does not return within the configured timeout, partitions are still reassigned.

## 14. Retries and Dead Letters Across Restarts

When a listener throws an exception, the Spring Kafka error handler can retry the record with backoff, recover it, or send it to a dead-letter topic (DLT). When a service restarts mid-retry, understand where retry state lives.

### 14.1. Blocking Retries in the Listener Container

Blocking retries normally execute inside the consumer/container processing path. If the process stops between attempts, uncommitted records can be redelivered once the service recovers. In-memory retry counters must not be treated as durable retry history across restarts.

Therefore:

- Design handlers to re-execute safely.
- Bound retries/backoff so partitions are not held too long.
- Separate transient errors from errors unrecoverable via retry.
- Track delivery counts via appropriate metadata/logs if long-term auditing is needed.

### 14.2. Retry Topics and DLTs

With non-blocking retry topics (`@RetryableTopic`) or retry mechanisms that publish records to separate topics, retry state is stored in Kafka records and survives restarts subject to retry topic retention. Still, explicitly configure attempt limits, backoff, DLT routing, and how records are recovered from the DLT.

Do not assume retry topics automatically preserve global ordering with the source topic. When events for the same aggregate move to a retry topic, later events in the source partition may proceed depending on the retry model; evaluate ordering requirements carefully.

### 14.3. Records in the DLT Need a Replay Process

The DLT should retain enough metadata for investigation: original topic, partition, offset, exception, timestamp, event ID, and correlation ID. Replaying must verify whether the event is still valid, whether it is a duplicate, and whether it could trigger repeated side effects.

Never auto-forward the entire DLT back to the source topic in an infinite loop. Maintain controlled replay procedures, record who/what triggered them, and monitor results.

## 15. Kafka Transactions and Database Transactions Across Restarts

Kafka transactions can coordinate output records and consumed offsets within the same Kafka transaction when configured properly. If the transaction aborts, offsets sent inside the transaction are rolled back alongside output records.

However, Kafka transactions do not automatically include JDBC transactions or HTTP calls. If a listener updates a database and then commits a Kafka offset, a failure window still exists between the two systems.

For workflows requiring consistency between database and events:

- **Inbox/idempotency:** record processed events inside the same DB transaction as business updates.
- **Transactional outbox:** persist business updates and outbound events in the same DB transaction, then relay outbox rows to Kafka.
- **Reconciliation:** reconcile business state against events/offsets after prolonged incidents.

Choose the pattern matching your consistency requirements. Never describe a listener as exactly-once for a database merely because it uses a Kafka `AckMode` or Kafka transactions.

## 16. Testing Restart Behavior

Restart tests must verify offsets, side effects, and consumer group state. A test proving only that the application context boots again is insufficient.

An integration test scenario with Testcontainers or `@EmbeddedKafka`:

1. Create a topic with at least one partition and a fixed group ID, e.g., `billing-restart-test`.
2. Send three events with distinct `eventId` values.
3. Start the listener with `AckMode.RECORD` and wait for the first two events to process/commit.
4. Trigger a controlled stop before the third event is acknowledged, or kill the test process while the handler is running.
5. Restart the listener with the same group ID.
6. Verify the listener resumes from the committed offset and the uncommitted event is redelivered.
7. Repeat the case where the database commits successfully yet the offset remains uncommitted; verify inbox/unique constraints prevent duplicate side effects.
8. Test a new group ID to prove `auto.offset.reset` applies when no committed offsets exist.
9. Verify retries/DLT and logs/metrics after restart.

With an in-JVM embedded broker, you can stop and restart listener containers via `KafkaListenerEndpointRegistry` to simulate part of the lifecycle. For genuine crash testing, Testcontainers or separate processes are better because processes can be killed mid-flight.

Synchronize with `CountDownLatch`, `BlockingQueue`, container callbacks, or offset polling with timeouts. Avoid fixed `Thread.sleep()` calls as proof that a listener committed offsets.

## 17. Observing Services Before and After Restarts

Capture the following in logs and metrics:

| Information | Purpose |
| --- | --- |
| Application instance/pod ID | Know which instance is processing |
| Consumer group ID | Track group progress |
| Consumer/client ID | Distinguish members within a group |
| Topic, partition, offset | Pinpoint exact record and read position |
| Event ID / aggregate ID | Traceability and idempotency checks |
| Processing result | Distinguish success, retry, recovery, and DLT |
| Commit failures | Detect completed side effects whose offsets failed to save |
| Rebalance count/duration | Assess restart/scaling impact |
| Consumer lag | Determine whether the group is keeping up with producers |

Metrics that should trigger alerts:

- Consumer lag climbing continuously after the service becomes ready.
- Consumer group having zero members while the service is expected to run.
- Repeated rebalances within a short window.
- Spikes in commit failures or deserialization errors.
- Abnormal growth in retry topics/DLTs.
- Shutdown duration exceeding termination grace periods.

## 18. Common Mistakes When Designing for Restarts

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Re-reads many events after restart | Offsets uncommitted or `BATCH` had not committed prior poll | Check AckMode and committed offsets; make handlers idempotent |
| Skips old events after restart | Used new group ID with `auto.offset.reset=latest`, or committed before side effects | Keep group ID stable; check reset policy and ack placement |
| Event applied twice | Database committed before Kafka offset committed | Use event IDs and inbox/unique constraints |
| Service starts yet receives no events | Container unstarted, group rebalancing, wrong topic/group config, or no assignments | Inspect registry, group membership, subscriptions, and logs |
| Reads from wrong offset after long outage | Committed offset expired or fell outside log retention | Check offset retention, topic retention, and `auto.offset.reset` |
| Deployment causes severe lag spike | Simultaneous restarts and rebalances | Use rolling deployments, graceful shutdown, and monitor rebalances |
| Listener killed mid-processing | Shutdown timeout too short or process received SIGKILL | Increase grace period appropriately, shorten handlers, and ensure idempotency |
| Retries restart from scratch after reboot | Blocking retry state is not persisted durably | Use retry topics or persist attempt state if business rules require |
| Static member fenced | Duplicate `group.instance.id` across instances | Assign a unique, stable ID to each consumer member |
| DLT replay creates duplicate side effects | Replay did not verify already-applied events | Enforce idempotency and audit replay operations |

## 19. Deployment Checklist

Before shipping a Kafka service to production, verify:

1. `group.id` is stable across restarts and across replicas of the same consumer group.
2. `enable.auto.commit=false` when letting the Spring Kafka container manage offsets.
3. `AckMode` matches processing boundaries and batch vs. record listeners.
4. Business side effects complete before acknowledging offsets.
5. Handlers are idempotent by `eventId` or appropriate business key.
6. Topic retention and consumer offset retention cover expected downtime durations.
7. `auto.offset.reset` is chosen deliberately for groups lacking offsets.
8. Spring lifecycle allows enough time to stop listeners; orchestrator grace periods align.
9. Listener dependencies close only after listeners stop.
10. Retries, retry topics, and DLTs have explicit recovery policies.
11. Readiness reflects listener status if the service is ready only after joining the group.
12. Monitoring covers group members, assignments, lag, commit failures, retries, and rebalances.
13. Integration tests verify restarts before processing, after side effects before commit, and with new groups.

A service restarts safely when it resumes from the right group's committed offsets, stops listeners gracefully, and can reprocess events without duplicating business effects. Kafka provides offset tracking and partition reassignment; applications must design commit boundaries, idempotency, and operational procedures to turn those mechanisms into reliable recovery.

## 20. Self-Check

1. Why must a service keep the same `group.id` across restarts to resume from committed offsets?
2. Does `auto.offset.reset=earliest` cause a group with valid offsets to re-read from the beginning?
3. What happens if a database transaction commits successfully but the process stops before committing the Kafka offset?
4. Why do `AckMode.RECORD` and `BATCH` differ in redelivery scope?
5. How does an inbox table prevent an event from creating duplicate side effects?
6. Why is it important to distinguish topic retention from consumer offset retention?
7. How does graceful shutdown of Kafka listeners differ from `server.shutdown=graceful`?
8. When is static membership with `group.instance.id` useful, and why must the ID be unique?
9. Is blocking retry state durably persisted across process restarts by default?
10. Which scenarios should be tested to prove a service recovers properly after a restart?
