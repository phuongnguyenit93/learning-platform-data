# Transaction Aborted or Producer Fenced

## 1. Symptoms and Impact

Kafka transactions let a producer write multiple records and commit them as one atomic unit. If a transaction aborts, consumers configured with `read_committed` will not receive records from that transaction. If a producer is fenced, the old producer loses authority to use that transactional ID and cannot continue transactions.

Common signs:

- Logs contain `ProducerFencedException`, `InvalidProducerEpochException`, or messages saying the producer was rejected due to an old epoch.
- `KafkaTemplate` sends records yet `commitTransaction()` fails.
- Listener transactions roll back and records are redelivered.
- `read_committed` consumers do not see records previously sent by the producer.
- Application repeatedly creates new producers or transactions abort after every rollout.
- Broker logs show transaction coordinator errors, transactional ID authorization errors, or transaction timeouts.

An abort can be the expected outcome when business processing fails. Fencing usually indicates another producer owns the same transactional ID, or the current producer became stale. Distinguish both cases before changing configurations.

## 2. Transactions, Producer ID, and Epoch

Kafka assigns a transactional producer a `transactional.id`. When the producer initializes transactions (`initTransactions()`), the broker assigns a producer ID and an epoch to that identity. The epoch is a generation number used to distinguish the current producer from older ones.

If a new producer initializes with the same `transactional.id`, Kafka bumps the epoch. The older producer with a lower epoch is fenced; subsequent requests from the old producer are rejected.

```text
transactional.id = orders-producer-1

Producer A initializes
  producerId = 700
  epoch      = 3
       |
       | Producer A starts transaction
       v
Kafka transaction coordinator
       ^
       | Producer B re-initializes same transactional.id
       |
Producer B
  producerId = 700
  epoch      = 4

Producer A (epoch 3) ---- next request ----> fenced
Producer B (epoch 4) ---- next request ----> valid
```

Fencing protects data against an old producer continuing writes after a new producer took over the same transactional ID. It is not a transient glitch you can fix by retrying with the same producer.

## 3. Distinguishing Aborts, Fencing, and Related Errors

| Exception / symptom | Meaning | How to handle |
|---|---|---|
| `ProducerFencedException` | Producer was replaced by another producer with a newer epoch | Stop reusing the old producer; find duplicate transactional IDs or stale producers |
| `InvalidProducerEpochException` | Request used a producer epoch that is no longer valid | Inspect producer lifecycle, fencing, and transaction state |
| `OutOfOrderSequenceException` | Producer sequence is invalid; can be fatal for idempotent/transactional producers | Inspect retries, producer lifecycle, and brokers; old producer may need discarding |
| `InvalidTxnStateException` | Operation invalid for current transaction state | Check begin/send/commit/abort sequence and shared producer usage |
| `TimeoutException` | A transaction operation did not complete in time | Distinguish timeouts during send, commit, coordinator lookup, or long-open transactions |
| `TransactionalIdAuthorizationException` | Principal lacks permission to use transactional ID | Grant appropriate `TransactionalId` ACL |
| `NotCoordinatorException` / coordinator unavailable | Client cannot reach the current transaction coordinator | Check broker/coordinator; let Kafka client handle retriable errors per config |
| `FencedInstanceIdException` | Static consumer member replaced by another consumer sharing `group.instance.id` | Fix consumer instance ID; this is not producer transaction fencing |
| `CommitFailedException` | Consumer cannot commit offsets, usually after losing assignments or rebalancing | Investigate consumer group, poll intervals, and offset commits |

`ProducerFencedException` and `FencedInstanceIdException` are two different errors. The first involves transactional producer IDs; the second involves static consumer membership.

## 4. Common Causes of Producer Fencing

### 4.1. Two Application Instances Share the Same Transactional ID

Check this first whenever errors appear after scaling or deploying multiple replicas. Two JVMs initializing the same transactional ID bump each other's epochs. Every time a new instance starts, the older producer gets fenced.

Example misconfiguration:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-
```

If every pod uses the same prefix and each pod has its own producer factory, suffixes generated inside each factory will collide. The prefix must distinguish concurrently running application instances.

### 4.2. Old Producer Still Alive After Restart or Network Partition

A process may lose connectivity briefly without shutting down completely. A new process initializes the same transactional ID and increments the epoch. When the old process reconnects, its requests are fenced.

### 4.3. Multiple Producers Share a Factory with Mismanaged Lifecycles

Spring Kafka's `DefaultKafkaProducerFactory` manages transactional producers and suffixes for them. Manually creating multiple factories with the same prefix, or holding onto old producers outside the factory, can trigger unexpected collisions.

### 4.4. Non-Unique Static Deployment Identity

A Kubernetes Deployment runs multiple replicas all sharing one fixed environment variable as the prefix. When scaled up, all replicas share one identity. Each pod needs an ID that is unique and stable over that pod's lifecycle.

## 5. Configuring Transactional IDs Properly in Spring Kafka

Spring Kafka uses `transactionIdPrefix` on `DefaultKafkaProducerFactory`. The factory appends a suffix to create a unique transactional ID for each producer it allocates.

Spring Boot example:

```yaml
spring:
  kafka:
    bootstrap-servers: broker1:9092,broker2:9092
    producer:
      transaction-id-prefix: ${HOSTNAME:local}-orders-tx-
```

In Kubernetes, `HOSTNAME` is typically the pod name. Verify that this variable truly differs across replicas and is not overridden to a shared constant.

The fallback value `local` is only suitable for single-instance development. In production, require `HOSTNAME` or `APP_INSTANCE_ID` to be set; if missing, fail fast rather than letting multiple replicas silently share the same prefix.

When creating the factory manually:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;

@Bean
DefaultKafkaProducerFactory<String, String> orderProducerFactory(
        @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers,
        @Value("${app.instance-id}") String instanceId) {

    Map<String, Object> properties = new HashMap<>();
    properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

    DefaultKafkaProducerFactory<String, String> factory =
            new DefaultKafkaProducerFactory<>(properties);

    factory.setTransactionIdPrefix(instanceId + "-orders-tx-");
    return factory;
}
```

`instanceId` must be unique across concurrently running processes. In this example, each factory manages internal suffixes so producers issued by the same factory do not collide on transactional IDs.

Never set the same static `transactional.id` directly on every producer. When using Spring Kafka, configure the prefix on the factory so the factory manages producer lifecycles and suffixes.

## 6. Inspecting Actual Transactional IDs

Do not rely only on the prefix in YAML. Inspect the transactional ID the producer actually uses in logs and runtime configuration.

Steps:

1. Log `HOSTNAME`, pod name, application instance ID, and transaction ID prefix at startup.
2. Compare instances within the same environment and cluster.
3. Check whether multiple `DefaultKafkaProducerFactory` beans share the same prefix.
4. Check whether producer factories are instantiated manually multiple times outside the Spring context.
5. Check whether old processes remain alive after rollouts, graceful shutdowns, or node partitions.
6. Correlate `ProducerFencedException` timestamps with another instance starting up.

Never log credentials, JAAS configs, or sensitive data when debugging transaction IDs.

## 7. Transactional IDs Must Be Unique Across Instances Yet Stable Within an Instance

Two requirements must be balanced:

- Concurrent instances must use distinct transactional IDs so they do not fence each other.
- A re-initialized producer for the same logical instance can intentionally reuse its prefix/ID so Kafka fences the old producer and ensures only the new one owns transactions.

Example with a Kubernetes StatefulSet:

```yaml
env:
  - name: APP_INSTANCE_ID
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
```

The application uses `APP_INSTANCE_ID` to build the prefix. StatefulSet ordinals stay stable when a pod is recreated while remaining distinct across replicas.

With Deployments, pod names normally change on every new pod. That safely prevents conflicts across running pods, though note that brand-new transactional IDs create new state entries in the transaction coordinator. Monitor transactional ID counts and expiration cleanup; never generate a fresh random prefix per producer inside the same factory.

Do not use the node hostname if multiple pods on the same node can run the same service and share that hostname.

## 8. What to Do When a Producer Is Fenced

Once a producer receives `ProducerFencedException`, the old producer no longer holds write permission for transactions. Never retry `send()` or `commitTransaction()` on that same producer as if it were a transient network blip.

Handling workflow:

1. Stop using the fenced producer.
2. Let Spring Kafka/the producer factory discard the failed producer per factory lifecycle; do not hold stale references for reuse.
3. Locate the other instance using the same transactional ID or prefix.
4. Fix the instance ID/prefix so each application instance has a distinct identity.
5. Ensure the old instance has shut down or stopped writing.
6. Obtain a new producer through the factory and start a new transaction.
7. Check records from the old transaction on a `read_committed` consumer to confirm they are invisible if the transaction aborted.

Never catch `ProducerFencedException` and ignore it to keep a listener running. An old producer cannot regain transaction ownership through retries.

## 9. Why Do Transactions Abort?

A transaction can abort because:

- The listener or service threw an exception before commit.
- The application explicitly called `abortTransaction()`.
- The producer was fenced by another producer.
- The transaction exceeded `transaction.timeout.ms`.
- The broker transaction coordinator failed or remained unavailable too long.
- Commit could not complete before timeout.
- The application sent offsets or records outside a valid transaction state.
- The principal lacks write permission on the topic or transactional ID.

An abort is a transaction rollback. Records sent in an aborted or uncommitted transaction stay hidden from consumers configured with `isolation.level=read_committed`.

With `read_uncommitted` consumers (the Kafka client default), records from aborted transactions can still be read. Therefore, when testing transactions, configure consumers with `read_committed` to verify atomic visibility.

## 10. Distinguishing Transaction Timeout from Poll Timeout

These timeouts govern different operations:

| Setting | Meaning | Sign when exceeded |
|---|---|---|
| `transaction.timeout.ms` | Max time the broker allows a transaction to remain open | Broker may abort the overdue transaction |
| `transaction.max.timeout.ms` | Max client transaction timeout accepted by the broker | Producer config exceeding this limit is rejected on init |
| `max.poll.interval.ms` | Max gap between consumer polls in the classic protocol | Consumer may leave the group; offset commits may fail |
| `request.timeout.ms` | Time client waits for a response to one request | Request times out, though transaction is not necessarily aborted right away |
| `delivery.timeout.ms` | Time cap for producer to deliver a record or report failure | Send future fails with delivery timeout |

Do not raise all timeouts simultaneously. Pinpoint which operation timed out and how long transactions/listeners genuinely hold resources.

Example producer configuration:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${HOSTNAME:local}-orders-tx-
      properties:
        "[transaction.timeout.ms]": 60000
        "[request.timeout.ms]": 30000
        "[delivery.timeout.ms]": 120000
```

These numbers are illustrative. `transaction.timeout.ms` must be less than or equal to the broker's `transaction.max.timeout.ms`. Do not set transaction timeouts longer than business needs because long-open transactions retain transaction coordinator state and can stall downstream `read_committed` consumers.

## 11. Checking the Transaction Coordinator and Brokers

The Kafka transaction coordinator tracks transactional IDs, producer epochs, and transaction state. If the coordinator is unavailable or transferring leadership, producers can see `NotCoordinatorException`, `CoordinatorNotAvailableException`, or `CoordinatorLoadInProgressException`.

Check:

- Which broker serves as coordinator for the transactional ID.
- Broker logs for transaction state log errors, disk errors, or ISR shrinks.
- Whether the cluster has enough brokers to satisfy the transaction state log's replication factor.
- Whether `transaction.state.log.replication.factor` and `transaction.state.log.min.isr` fit the broker count and desired durability.
- Whether broker restarts, leader elections, or network partitions coincide with the errors.
- Whether the producer relies on Kafka client coordinator retries or the app adds excessive manual retries.

In multi-broker production clusters, the transaction state log needs proper replication so transaction metadata does not become a cluster weak spot. Do not lower replication factor/min ISR just to get transactions working on an undersized cluster without assessing risk.

If multiple producers with different transactional IDs hit coordinator errors together, suspect the broker/cluster. If only one ID repeatedly gets fenced while the coordinator stays healthy, focus on ID collisions and producer lifecycles.

## 12. Transactional ID Authorization and Kafka ACLs

When using SASL/SSL or another authentication mechanism, producers need permissions on related resources. Missing transactional ID permissions can throw `TransactionalIdAuthorizationException` when initializing transactions or sending transactional requests.

Check these permissions:

| Resource | Typical operations needed | Purpose |
|---|---|---|
| `TransactionalId` | `Write`, `Describe` per operation/version | Initialize and use transactional ID |
| Source/target topics | `Write`, `Describe` | Write records inside transactions |
| Consumer Group | `Read` | Consumer joins group and sends offsets to transaction |

Exact ACLs depend on the broker authorizer, principal mapping, and actual operations. Grant least-privilege permissions to the service's transactional ID prefix; avoid broad permissions across all transactional IDs.

If the failure is authorization, changing `transactionIdPrefix` will not fix missing permissions. Inspect the principal seen by the broker and verify ACL resource types.

## 13. Configuring `KafkaTransactionManager` in Spring Kafka

To use `@Transactional` with Kafka, the producer factory must have a transaction ID prefix and the application must declare `KafkaTransactionManager`.

```java
@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
            ProducerFactory<String, OrderEvent> producerFactory) {

        return new KafkaTransactionManager<>(producerFactory);
    }
}
```

A service can participate in a transaction by referencing the matching transaction manager:

```java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(OrderEvent event) {
        kafkaTemplate.send("orders", event.orderId(), event);
        kafkaTemplate.send("orders.audit", event.orderId(), event);
    }
}
```

Sends performed within the same Kafka transaction are thread-bound by Spring. When the method finishes normally, the transaction manager commits; if it throws a matching exception, the transaction rolls back/aborts.

The `KafkaTemplate` in the service must use the same `ProducerFactory` managed by `KafkaTransactionManager`. If the template and transaction manager point to two different factories, sends will not join the expected transaction.

Ensure the method is invoked through a Spring proxy. Self-invocation inside the same bean bypasses `@Transactional`; no Kafka transaction opens as expected. Calling from another thread or `@Async` also does not propagate thread-bound transactions automatically.

## 14. Transactional Listener Containers and Offsets

With a transactional listener container, Spring Kafka begins a Kafka transaction for processing a record. When the listener succeeds, the container sends the processed offset into the transaction and commits. If the listener throws an exception, the transaction aborts; the record can be redelivered per the error handler and offset commit policy.

Example configuring the factory with a transaction manager:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);
    return factory;
}
```

The listener container's `ConsumerFactory` creates consumers and must point to the right cluster and security config. `KafkaTransactionManager` manages producer transactions; any `KafkaTemplate` emitting outputs within the transaction must share the same `ProducerFactory` as the transaction manager.

Listener:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-projection",
        containerFactory = "orderListenerFactory")
public void onOrder(OrderEvent event) {
    projectionService.apply(event);
}
```

If the listener throws an exception, the container rolls back the transaction. `AfterRollbackProcessor` handles redelivery or recovery after retry exhaustion; `DefaultAfterRollbackProcessor` is the default implementation in transactional listener flows. Never catch and merely log exceptions if you expect rollback; swallowing exceptions can cause the container to treat the listener as successful and commit offsets.

The listener container's transaction manager setter API varies across Spring Kafka lines. In current Spring Kafka, use `setKafkaAwareTransactionManager`; older codebases may use the deprecated `setTransactionManager`. Use the API matching your managed version.

## 15. Checking `isolation.level=read_committed`

Consumers default to `read_uncommitted`. To receive only records from committed transactions, configure:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

A `read_committed` consumer returns records only up to the Last Stable Offset (LSO), the position right before the earliest open transaction on that partition. A long-running open transaction can hold back newer records from the consumer even after those records were written.

When investigating “missing” records, verify:

- Did the producer commit or abort the transaction?
- Is the consumer using `read_committed` or `read_uncommitted`?
- Does the partition have a long-open transaction blocking LSO advancement?
- Is the consumer reading the right topic, partition, and offset?
- Have transaction markers been written and replicated by brokers?

If a record belongs to an aborted transaction, `read_committed` consumers hide it by design. That does not mean Kafka physically deleted the record from the log.

## 16. Transaction Timeouts and Long-Open Transactions

A transaction should wrap a bounded unit of work. If the application opens a transaction and then makes slow HTTP calls, waits on user input, or processes huge batches, the transaction can exceed `transaction.timeout.ms`.

Best practices:

- Avoid slow non-Kafka I/O inside a Kafka transaction whenever unnecessary.
- Set timeouts on database/HTTP calls.
- Keep transactional batches small enough.
- Never open a transaction and hold the producer idle across interactive steps.
- Monitor transaction duration and abort rates.
- Size `transaction.timeout.ms` from p99 processing duration and broker caps.

Transaction timeout protects brokers from abandoned transactions. Raising the timeout is justified only when business logic genuinely takes longer and cluster impact has been evaluated.

## 17. Producer Factory Cache and Producer Lifecycle

Spring Kafka's `DefaultKafkaProducerFactory` manages producers created from the factory. For transactional producers, the factory builds transactional IDs from prefix plus suffix; producers can be cached and reused according to lifecycle rules.

Check:

- How many producer factories exist in the application context?
- Do multiple factories share the same prefix?
- Are more threads/concurrent transactions running than the producer cache permits?
- Does the application retain producers outside the factory or call `close()` improperly?
- Do old producers survive too long after a pod is replaced?
- Is `maxAge` configured so producers refresh before transactional IDs expire?

Spring Kafka provides `setMaxAge(Duration)` on the producer factory to cap cached producer age. This helps when brokers configure `transactional.id.expiration.ms`; a producer cached too long can hold an expired transactional ID and fail when starting a new transaction. Set max age lower than broker expiration with safety margin.

`setMaxAge()` was introduced in Spring Kafka 2.5.8, 2.6.4, and 2.7.0 on their respective branches. On older versions, verify API availability first. Never apply a blanket max age without checking the broker's `transactional.id.expiration.ms`.

Example:

```java
factory.setMaxAge(Duration.ofHours(6));
```

Six hours is illustrative only. Cross-check with broker `transactional.id.expiration.ms` and actual producer usage lifetimes.

## 18. Nested Transactions and `executeInTransaction`

`KafkaTemplate.executeInTransaction()` creates a local transaction around a send callback:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders", orderId, orderEvent);
    operations.send("orders.audit", orderId, auditEvent);
    return null;
});
```

If the callback throws an exception, the transaction aborts; on normal completion, the template commits. This API works well when scoping a transaction to a clear block of code.

`executeInTransaction()` manages the callback's local transaction; do not assume it automatically joins an active transaction bound by `KafkaTransactionManager`. When mixing with `@Transactional`, check your Spring Kafka version's semantics to avoid accidentally running two separate transactions while thinking they are one.

Do not nest multiple transactions on the same producer casually. When combining `@Transactional`, `KafkaTransactionManager`, and `executeInTransaction()`, clarify which transaction owns the producer and which is independent. Verify propagation semantics in your Spring Kafka version before nesting transactions.

If a transaction has been fenced, do not call `executeInTransaction()` again on the stale producer. Fix the transactional ID root cause and let the factory supply a valid new producer.

## 19. Distinguishing Kafka Transactions from Database Transactions

Kafka transactions are atomic only within Kafka: writing multiple Kafka records and sending consumer offsets in the same transaction. They do not automatically create distributed atomic transactions with databases.

For example, `@Transactional("kafkaTransactionManager")` manages only the Kafka transaction. If the method also writes to a database via JDBC/JPA, database and Kafka transactions can commit at different times depending on transaction managers and synchronization.

Do not assume both database and Kafka roll back together just because `@Transactional` is present. When needing reliable event publication after database commits, consider Transactional Outbox with CDC relay; when consumers update databases, use Inbox/idempotency to prevent duplicate processing.

## 20. Inspecting Producer Transactions via CLI and Logs

Kafka does not provide one simple CLI command to list all open transactions by transactional ID across every version. Combine producer logs, broker logs, consumer visibility, and metrics during investigation.

Check producer:

- Record application instance ID, transactional ID prefix, producer client ID, and startup time.
- Search for `ProducerFencedException`, `InvalidProducerEpochException`, `TimeoutException`, and `TransactionalIdAuthorizationException`.
- Pinpoint whether the exception occurred in `initTransactions`, `beginTransaction`, `send`, `sendOffsetsToTransaction`, `commitTransaction`, or `abortTransaction`.
- Track transaction duration and commit/abort counts.

Check broker:

- Transaction coordinator and broker logs.
- Transaction state log replication/ISR.
- Coordinator movements, broker restarts, and network health.
- ACLs for transactional IDs and topics.

Check consumer:

- Configured `isolation.level`.
- Consumer lag and Last Stable Offset if metrics are available.
- Whether records belong to aborted or still-open transactions.
- Whether offset commits join the same transaction in consume-transform-produce flows.

Do not leave full Kafka protocol debug logging enabled long-term in production. Enable verbose logging only for a bounded window while safeguarding sensitive data.

## 21. Error and Remediation Table

| Error | Common cause | Action |
|---|---|---|
| `ProducerFencedException` | Multiple producers share a transactional ID; old producer still alive | Give each instance a unique prefix; stop old producers; never retry fenced producer |
| `InvalidProducerEpochException` | Stale producer epoch or invalid transaction state | Check transactional ID collisions and lifecycle |
| `OutOfOrderSequenceException` | Sequence/epoch mismatch from producer state or retries | Discard broken producer, check client/broker, and do not reuse old instance |
| `InvalidTxnStateException` | Calling commit/abort/send in invalid state or misusing producer concurrently | Check transaction lifecycle and producer ownership |
| `TransactionalIdAuthorizationException` | Missing ACL on transactional ID | Grant `TransactionalId` permission to the right principal |
| `TimeoutException` on commit | Slow coordinator, long-open transaction, or incomplete request | Check coordinator, timeouts, and transaction duration; verify commit outcome before retrying business work |
| `CoordinatorNotAvailableException` | Transaction coordinator unavailable | Check broker/coordinator and network; let client handle retriable errors |
| `CommitFailedException` in listener | Consumer lost assignment or group rebalanced | Check poll interval, listener duration, and group membership |
| Consumer misses records | Transaction aborted or consumer uses `read_committed` while transaction stays open | Check transaction outcome, LSO, and isolation level |
| Aborts climb when downstream slows | Transaction held open waiting on dependencies | Shorten transactions, add dependency timeouts, or decouple workflow |
| Fencing after scaling deployment | Replicas share the same prefix | Tie prefix to unique pod/instance ID |
| Old producer fenced after restart | Old producer not stopped or same ID reused | Check shutdown, rollouts, and ID ownership |

If `commitTransaction()` times out, the client might not know whether the broker committed because the response could be lost in transit. Do not assume the transaction aborted solely from a client timeout. Verify via a `read_committed` consumer, event ID/idempotency, and coordinator logs before re-executing business side effects.

## 22. Testing Transaction Aborts and Fencing

Write integration tests against a transaction-capable broker rather than mocking `KafkaTemplate` alone.

### Test Abort Hides Records from `read_committed`

1. Create a transactional producer.
2. Begin a transaction and send a record.
3. Call `abortTransaction()`.
4. Read the topic with a `read_committed` consumer.
5. Assert the record from the aborted transaction is not returned.

### Test Commit Makes Records Visible

1. Begin a transaction.
2. Send one or more records.
3. Call `commitTransaction()`.
4. `read_committed` consumer receives all records.
5. Assert metadata/offsets and payloads.

### Test Fencing

1. Create producer A with transactional ID `orders-test-1`.
2. Call `initTransactions()` and start a transaction.
3. Create producer B with the same transactional ID and call `initTransactions()`.
4. Assert producer A is fenced when continuing transaction operations.
5. Assert producer B proceeds with the new epoch.

Run this test sequentially and close both producers. Never run concurrent tests using the same transactional ID.

### Test Spring Factory Prefix

- Start two application instances with distinct prefixes and verify they do not fence each other.
- Start two factories with identical prefixes and verify tests detect the conflict.
- Test `maxAge` and producer refresh against test broker config.
- Test transaction rollback when a listener throws an exception.
- Test that offsets and output records commit atomically in consume-transform-produce.

## 23. Quick Investigation Workflow

1. **Classify the error:** abort, producer fence, authorization, coordinator timeout, or static consumer member fence.
2. **Locate the operation:** did it fail at init, begin, send, send offsets, commit, or abort?
3. **Capture identities:** transactional ID/prefix, application instance ID, pod name, and producer client ID.
4. **Compare instances:** search for two processes sharing the same prefix/transactional ID at the same time.
5. **Inspect lifecycles:** check old producers, old pods, graceful shutdowns, and network partitions.
6. **Inspect timeouts:** compare transaction duration against `transaction.timeout.ms` and broker max timeout.
7. **Inspect coordinator:** broker logs, coordinator movement, transaction state log, and network.
8. **Inspect ACLs:** verify principal permissions on transactional ID, topic, and consumer group.
9. **Inspect consumer visibility:** `read_committed` vs. `read_uncommitted`, whether transaction committed, and whether LSO is blocked.
10. **Fix one root cause:** usually starting with prefix uniqueness or transaction duration.
11. **Create fresh producer:** only after removing stale/fenced producers and verifying IDs.
12. **Re-test:** commit, abort, fencing, restarts, and multi-instance rollouts.

## 24. Prevention Checklist

- [ ] Every application instance has a unique `transactionIdPrefix`.
- [ ] Producers in the same factory are managed by `DefaultKafkaProducerFactory`.
- [ ] Fenced producers are never retained or reused.
- [ ] Transactions have bounded lifetimes shorter than the broker max timeout.
- [ ] Dependency timeouts prevent transactions from staying open too long.
- [ ] Consumers use `read_committed` when aborted-transaction records must stay hidden.
- [ ] Kafka ACLs grant proper permissions for transactional IDs, topics, and consumer groups.
- [ ] Transaction coordinator and transaction state log have proper replication/ISR.
- [ ] Producer factory `maxAge` fits `transactional.id.expiration.ms`.
- [ ] Shutdowns/rollouts never leave old producers running out of control.
- [ ] Metrics track commits, aborts, duration, fencing, and coordinator errors.
- [ ] Integration tests cover commit, abort, fencing, and multiple instances.

## 25. Summary

- Transaction abort rolls back a Kafka transaction unit; uncommitted records remain invisible to `read_committed` consumers.
- `ProducerFencedException` occurs when a producer uses a stale epoch because another producer took over the transactional ID.
- Spring Kafka's `transactionIdPrefix` must be unique per application instance; the factory manages per-producer suffixes.
- A fenced producer cannot recover via retries on the same instance; discard it and fix the ID collision or lifecycle bug.
- `transaction.timeout.ms` differs from `max.poll.interval.ms`, `request.timeout.ms`, and `delivery.timeout.ms`.
- Transaction coordinators, transaction state logs, `TransactionalId` ACLs, and networking can all trigger transaction failures.
- `KafkaTransactionManager` and transactional listener containers let Spring manage transactions; swallowed exceptions can cause unwanted commits.
- `read_committed` is essential when verifying atomic visibility of transactions.
- Kafka transactions are not automatically atomic with databases; use Outbox/Inbox when coordinating DB and Kafka.
- Track transaction IDs, producer epochs, durations, abort rates, coordinators, and consumer visibility for evidence-based diagnosis.

When transactional IDs are isolated per instance and transactions stay short-lived, producers avoid identity-collision fencing. When a transaction genuinely aborts, consumers and error handlers can act on accurate commit/rollback semantics rather than retrying blindly.

## References

- [Apache Kafka — Transactional Messaging](https://kafka.apache.org/documentation/#semantics)
- [Apache Kafka — Producer Configs](https://kafka.apache.org/41/configuration/producer-configs/)
- [Apache Kafka — Broker Configs](https://kafka.apache.org/41/configuration/broker-configs/)
- [Apache Kafka — Authorization and ACLs](https://kafka.apache.org/documentation/#security_authz)
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka — Producer Factory](https://docs.spring.io/spring-kafka/reference/kafka/producer-factory.html)
- [Spring Kafka — Container Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html#container-transaction)
