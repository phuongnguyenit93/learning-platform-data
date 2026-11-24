# Reason FENCED

In Spring Kafka, **Reason.FENCED** is a value of **ConsumerStoppedEvent.Reason**. It indicates that a consumer listener container has stopped after a **transactional Kafka producer was fenced**, provided the container's **stopContainerWhenFenced** property is enabled. This is an important lifecycle event in applications handling Kafka transactions, especially **consume → process → produce** flows.

FENCED does not simply mean a partition was rebalanced, nor is it the name of an exception thrown by a business listener. It is **a consumer stop reason recorded by Spring Kafka** when the container encounters a situation where the transactional producer no longer has authority to continue the transaction and policy requires stopping the container.

In a system requiring high reliability, you must understand why a producer gets fenced, which offsets may be uncommitted, whether the partition already belongs to another consumer, and when the container can be restarted without creating an error loop or executing duplicate side effects.

## 1. Where does Reason.FENCED appear?

Spring Kafka publishes application events for listener container lifecycles. An important event is **ConsumerStoppedEvent**, published after the consumer closes. This event has a **reason** explaining why it stopped.

Common reasons:

| Reason | Meaning |
|---|---|
| **NORMAL** | Consumer stopped per the container's normal lifecycle |
| **FENCED** | Transactional producer was fenced and container enabled stopContainerWhenFenced |
| **AUTH** | Encountered authentication/authorization failure without matching retry config |
| **NO_OFFSET** | No offset found and auto.offset.reset policy is none |
| **ERROR** | A serious java.lang.Error was thrown |
| **ABNORMAL** | Some Spring Kafka versions add an abnormal stop reason |

Exact enum constants may vary across versions. For this lesson, the target to recognize is:

~~~java
ConsumerStoppedEvent.Reason.FENCED
~~~

**Core condition**:

~~~text
Kafka transactional producer is fenced
              |
              v
Listener container receives fencing condition
              |
              v
stopContainerWhenFenced == true ?
              |
      +-------+-------+
      |               |
     true            false
      |               |
      v               v
Container stops    Do not infer there will be a
      |            ConsumerStoppedEvent
      v            with reason FENCED
ConsumerStoppedEvent
  reason = FENCED
~~~

Therefore, **not every ProducerFencedException guarantees receiving ConsumerStoppedEvent.Reason.FENCED**. You must account for the `stopContainerWhenFenced` policy and container lifecycle.

## 2. What is fencing in Kafka transactions?

Kafka transactions use **transactional.id** to identify a logical transactional producer. The Kafka broker/transaction coordinator manages the state, epoch, and transactions of that identity.

When another producer initializes with the same `transactional.id` or the coordinator determines the old producer is no longer valid, the old producer can be **fenced**. The old producer is prevented from continuing to commit transactions as a valid producer.

~~~text
Producer A
  transactional.id = orders-worker-1
  old epoch
        |
        | has an in-progress transaction
        v
Producer B initializes with same transactional.id
  new epoch
        |
        v
Coordinator invalidates producer A
        |
        v
Producer A continues send / commit
        |
        v
ProducerFencedException or related epoch error
~~~

Fencing is a **protective mechanism** to prevent two producers sharing a transactional identity from producing conflicting transaction outcomes. Do not treat broker fencing as merely a network error that can be infinitely retried on the old producer.

Once a producer is genuinely fenced, the application must let the producer go through proper closing/replacement lifecycle. Continuing to reuse that same producer for the next transaction is not a safe recovery path.

## 3. Why is FENCED tied to rebalancing?

In a consumer-initiated Kafka transaction, the listener container reads an input record, opens a Kafka transaction, sends outputs, and includes consumed offsets in the transaction. Kafka must ensure the consumer still has authority over the corresponding partitions when the transaction completes.

If the consumer group rebalances while a transaction is in progress, partitions may be reassigned to another member. The old consumer should no longer continue committing outputs/offsets as if it were still the valid owner.

Example:

~~~text
orders/P2@51 belongs to Consumer A
          |
          v
Consumer A begins Kafka transaction T1
          |
          +-- sends output in T1
          +-- listener takes too long
          |
          v
Rebalance occurs
          |
          v
P2 moves to Consumer B
          |
          v
Consumer A attempts to finish T1
          |
          v
Transaction hits fencing / commit failure
          |
          v
Container may stop with reason FENCED
~~~

The diagram shows a typical scenario of losing processing authority or transaction completion authority. **Do not assert that every rebalance causes ProducerFencedException**: most normal rebalances are handled via revoke/assign callbacks without stopping the container with reason FENCED.

Spring Kafka cannot always clearly distinguish whether producer fencing resulted from a rebalance, a transaction timeout, or `transactional.id` expiration. Because of that uncertainty, trying to seek partitions back when ownership may already be lost is dangerous.

## 4. How does Reason.FENCED differ from ProducerFencedException?

The two concepts belong to two different layers:

| Concept | Layer | Information conveyed |
|---|---|---|
| **ProducerFencedException** | Kafka client / producer | Producer no longer has authority to execute transactions with current identity |
| **ConsumerStoppedEvent.Reason.FENCED** | Spring Kafka listener container lifecycle | Consumer stopped due to producer fencing when stop-on-fence config is enabled |
| **onPartitionsRevoked** | Kafka consumer rebalance lifecycle | Partitions are about to be revoked |
| **onPartitionsLost** | Kafka consumer rebalance lifecycle | Consumer has lost partition ownership |

ProducerFencedException is the **technical cause**, whereas Reason.FENCED is the **lifecycle consequence signal** for the Spring application.

You may see ProducerFencedException in logs without seeing ConsumerStoppedEvent.Reason.FENCED if:

- `stopContainerWhenFenced` is not enabled.
- The error occurred outside the observed listener container.
- Another framework layer translated or handled the exception.
- The process stopped abruptly before publishing the lifecycle event.
- The listener container version or configuration behaves differently than assumed.

Conversely, once ConsumerStoppedEvent.Reason.FENCED is received, investigate real producer fencing rather than simply turning the listener back on as if it were a normal rebalance.

## 5. The stopContainerWhenFenced condition

Spring Kafka provides the **stopContainerWhenFenced** property on `ContainerProperties`. When set to **true**, the container stops when ProducerFencedException arises in the transaction processing path managed by the container; after the consumer closes, ConsumerStoppedEvent can carry reason FENCED.

The default value listed in Spring Kafka documentation across many versions is **false**. Therefore, if the system needs to accurately observe the stop-on-fence lifecycle, configure it explicitly and verify your current dependency version.

Example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        transactionalListenerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                KafkaTransactionManager<String, OrderResult> kafkaTxManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTxManager);
    factory.getContainerProperties()
            .setStopContainerWhenFenced(true);

    return factory;
}
~~~

The snippet illustrates a listener container with a Kafka transaction manager and stop-on-fence policy. `OrderCreated`/`OrderResult` types are example application models. The `ProducerFactory` used by `kafkaTxManager` must be configured as transactional.

Transaction manager setter names and wiring can differ across Spring Kafka versions, yet the configuration directly relevant to this lesson is:

~~~java
factory.getContainerProperties().setStopContainerWhenFenced(true);
~~~

Do not enable this property expecting it to **prevent** producers from being fenced. It does not prevent fencing; it determines how the listener container reacts **after** fencing occurs.

## 6. Flow of ConsumerStoppedEvent.Reason.FENCED

After a producer is fenced and the container decides to stop:

~~~text
Transactional listener container
       |
       v
Kafka transaction encounters producer fencing
       |
       v
Container receives fatal error for transaction
       |
       v
stopContainerWhenFenced = true
       |
       v
Container stops consumer
       |
       v
ConsumerStoppedEvent
  reason = FENCED
       |
       v
Spring @EventListener / ApplicationListener
       |
       +-- log incident
       +-- alert
       +-- update health/operational state
       +-- decide controlled restart
~~~

**ConsumerStoppedEvent is published after the consumer closes**, so this event is not the place to keep using the old `KafkaConsumer` to poll or commit offsets.

With a concurrent listener container, multiple child consumers can publish separate lifecycle events. One consumer getting fenced does not mean all child consumers stopped in the exact same callback; the scope of impact must be determined from container/child IDs and actual status.

## 7. Listening for Reason.FENCED in Spring

You can register a Spring application event listener:

~~~java
@Component
public class KafkaConsumerLifecycleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerLifecycleObserver.class);

    @EventListener
    public void onConsumerStopped(ConsumerStoppedEvent event) {
        ConsumerStoppedEvent.Reason reason = event.getReason();

        if (reason == ConsumerStoppedEvent.Reason.FENCED) {
            MessageListenerContainer stoppedContainer =
                    event.getSource(MessageListenerContainer.class);

            log.error(
                    "Kafka consumer stopped after producer fencing; " +
                    "listenerId={}, reason={}",
                    stoppedContainer.getListenerId(),
                    reason);

            // Record the incident and trigger controlled recovery workflow.
        }
    }
}
~~~

In the example, import `ConsumerStoppedEvent`, `MessageListenerContainer`, Spring `@EventListener`, and the corresponding logger. `getSource(MessageListenerContainer.class)` is the typed container retrieval method described in Spring Kafka documentation.

In systems with multiple listeners, also record instance ID, consumer group, `transactional.id` prefix, and timestamp. **Do not log full producer objects or Kafka credentials**.

Application events may be dispatched on the event-publishing thread depending on `ApplicationEventMulticaster` configuration. Do not manipulate `KafkaConsumer` from an async listener even if the event carries a consumer reference; `KafkaConsumer` is not an object that can be used freely across threads.

## 8. Should you restart the container immediately?

Spring Kafka allows retrieving the container reference from `ConsumerStoppedEvent` and restarting it. Documentation describes this capability for recovering from a FENCED situation.

However, **do not unconditionally restart immediately upon receiving Reason.FENCED**. If the cause is two application instances using duplicate `transactional.id`s, the freshly restarted container may immediately be fenced again by the other instance. The result is a loop:

~~~text
FENCED
   |
   v
stop container
   |
   v
restart immediately
   |
   v
new producer still uses conflicting transactional.id
   |
   v
FENCED again
   |
   v
restart loop
~~~

Safe recovery usually involves:

1. Identifying the failing instance and `transactional.id`.
2. Checking whether another producer is using the same `transactional.id`.
3. Reviewing restart, scaling, deployment, and rebalance history.
4. Checking transaction timeout and listener processing duration.
5. Closing/discarding the fenced producer per container lifecycle.
6. Restarting only once fencing conditions are resolved or under a controlled retry policy.
7. Limiting restart attempts, applying backoff, and alerting on continuous failures.

Do not call restart in an infinite loop inside a Spring event listener. For systems with many listeners, use a lifecycle coordinator or orchestration policy to track and control restarts at the application level.

## 9. Why should ProducerFencedException not be handled with standard retries?

Transient network errors can be retried on a healthy producer; **producer fencing** is fundamentally different. The broker has already deemed the current transactional identity/epoch invalid to continue transactions.

Dangerous example:

~~~java
try {
    kafkaTemplate.send("orders.result", result).join();
}
catch (Exception ex) {
    // Do not infinitely retry every exception on the same producer.
}
~~~

If the root error is fencing, repeatedly retrying on the old producer will not restore its authority. Instead, the system must let the transaction fail, close/replace the producer, and recover the consumer from a valid Kafka position.

With transactional listeners, exceptions must propagate to the container/transaction manager so the container executes the proper lifecycle. If business code catches and swallows a fatal transaction error, the container may misjudge processing status or fail late at commit time.

Do not turn `ProducerFencedException` into a regular business error to route immediately to DLT; DLT is usually meant for **unprocessable records**, whereas fencing is a **transactional infrastructure or ownership** failure.

## 10. Why may Spring Kafka skip AfterRollbackProcessor when fenced?

In a normal transactional listener, when a business listener throws an exception, the container rolls back the transaction and can then use **DefaultAfterRollbackProcessor** to seek/retry the record.

When a producer is fenced, the situation differs:

~~~text
Normal business exception
     |
     v
Kafka transaction rollback
     |
     v
AfterRollbackProcessor
     |
     v
Seek/retry under valid ownership

Producer fencing
     |
     v
Uncertain whether partitions are still owned
     |
     v
Should not seek blindly from old consumer
     |
     v
Container stops when stopContainerWhenFenced=true
~~~

Spring Kafka documentation notes that in rebalance-related fencing cases, the container cannot assume the consumer is still assigned the old partitions. Therefore, **it should not run after-rollback seeks like when handling a business exception**.

This distinction is critical: trying to seek or commit a partition no longer under management can fail or cause the application to make wrong recovery decisions.

When the partition is assigned to a new consumer, the new consumer resumes from the valid committed offset. Uncommitted records can be reprocessed according to application policy.

## 11. Reason.FENCED and onPartitionsRevoked

**onPartitionsRevoked** is the standard rebalance callback when a consumer is about to yield partitions; **Reason.FENCED** is the reason the container stopped because a transactional producer was fenced.

| Aspect | onPartitionsRevoked | ConsumerStoppedEvent.Reason.FENCED |
|---|---|---|
| API layer | ConsumerRebalanceListener / ConsumerAwareRebalanceListener | Spring Kafka application lifecycle event |
| When it occurs | During assignment revocation | After consumer closes due to fencing with stop policy enabled |
| Scope | A set of TopicPartitions being handed over | A stopped consumer/container |
| Guaranteed producer transaction error? | No | Has producer fencing cause |
| Guaranteed consumer already stopped? | No | Yes, ConsumerStoppedEvent publishes after consumer closes |
| Primary action | Flush/release state, coordinate commit if ownership remains | Investigate fencing, evaluate restart, and recover lifecycle |

Normal rebalances can occur daily during scaling, deployments, or membership changes. FENCED is usually a signal requiring more serious investigation because it involves the ability to continue Kafka transactions.

Do not assume every revoke is fencing, or that every Reason.FENCED was preceded by a revoke callback. A process can hit exceptions and stop along many different lifecycle paths.

## 12. Reason.FENCED and onPartitionsLost

**onPartitionsLost** indicates the consumer lost partition ownership without being able to hand over via a normal revoke path. In that case, do not continue committing offsets or writing state as the old owner.

Reason.FENCED can appear in the context of lost ownership or transactional identity, yet the two events are not synonymous:

~~~text
Consumer A processes P1@200
    |
    +-- P1 is assigned to Consumer B
    |
    +-- A encounters lost ownership
    |       (possibly with onPartitionsLost)
    |
    +-- A's producer transaction is fenced
    |
    +-- Container A stops with Reason.FENCED
            if stop-on-fence is configured
~~~

The diagram only describes one possible sequence, not a guarantee of callback order. If the process is killed or loses connectivity, you may not receive all expected events.

For both partition lost and producer fenced, **never manually commit offsets belonging to old partitions to "mark as processed"**. Let the new consumer resume from the Kafka-acknowledged committed offset, while protecting side effects with idempotency.

## 13. transactional.id must be unique across active instances

An easily controlled source of fencing is service instances using the same `transactional.id` prefix and ending up with duplicate actual producer identities.

Incorrect example:

~~~text
Pod A:
  transaction-id-prefix = orders-tx-
  transactional.id      = orders-tx-0

Pod B:
  transaction-id-prefix = orders-tx-
  transactional.id      = orders-tx-0

Pod A and Pod B are both active
-> can fence each other
~~~

A proper configuration must distinguish concurrently active instances:

~~~text
Pod A:
  transaction-id-prefix = orders-pod-a-tx-
  transactional.id      = orders-pod-a-tx-0

Pod B:
  transaction-id-prefix = orders-pod-b-tx-
  transactional.id      = orders-pod-b-tx-0
~~~

These are illustrative values; Spring Kafka `ProducerFactory` can generate multiple suffixes for transactional producers from the same prefix. **The goal is not merely prefixes looking different, but ensuring no actual transactional.id collides across active producer instances**.

When deploying on Kubernetes, note:

- Rolling updates can keep old pods and new pods alive simultaneously for a window.
- If using instance IDs derived from hostnames, verify uniqueness across pods.
- If using one fixed config for all replicas, collision risk rises.
- A new pod replacing an old pod reusing an identity can fence the old producer via Kafka mechanics; that can be desired behavior for fencing zombie instances, yet orchestration and shutdown must be evaluated.
- Increasing concurrency increases the number of transactional producers and suffixes the factory must manage.

Do not fix fencing errors merely by dropping Kafka transactions if the business requires outputs and consumed offsets to commit atomically.

## 14. transaction timeout and producer expiration

Not all fencing is caused by two pods sharing a `transactional.id`. Some cases involve **transaction.timeout.ms**, **transactional.id.expiration.ms**, or a producer staying idle too long.

Frequently confused settings:

| Parameter | Layer | Role |
|---|---|---|
| **transaction.timeout.ms** | Kafka transactional producer | Limits how long a transaction may remain open per broker policy |
| **transactional.id.expiration.ms** | Kafka broker | Duration after which an idle transactional identity can be expired from coordinator state per broker conditions |
| **max.poll.interval.ms** | Kafka consumer | Limits gap between poll calls under consumer group protocol |

Example:

~~~text
transaction.timeout.ms = 60 seconds

Listener:
  DB lock wait        40 seconds
  External API call   30 seconds
  Produce + commit     5 seconds
  ------------------------------
  Total               75 seconds
~~~

The transaction risks timing out before processing completes. When proceeding to commit, the producer can hit transactional state/fencing errors depending on situation and client version.

**Do not equate transaction timeout with max.poll.interval.ms.** One limit belongs to producer transactions, the other to consumer polling and group membership. Both must be accounted for in the listener processing budget.

If a transactional producer sits idle for a very long time, cached producers can also be affected by `transactional.id` expiration. Some Spring Kafka versions support `DefaultKafkaProducerFactory` `maxAge` to proactively replace cached producers before expiration.

## 15. Bounded transaction timeout configuration

Spring Boot configuration example:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-instance-a-tx-
      properties:
        "[transaction.timeout.ms]": 120000
    consumer:
      group-id: orders-transformer
      enable-auto-commit: false
      properties:
        "[max.poll.interval.ms]": 300000
~~~

The example illustrates a 120-second transaction timeout and 300-second max poll interval. These values are **not fixed production recommendations**. Brokers impose a maximum transaction timeout limit; producers cannot arbitrarily set a value higher than what the broker permits.

When tuning:

1. Measure actual transaction duration, including listener, produce, callbacks, and commit.
2. Measure p95/p99 latency of databases and downstream APIs.
3. Check `max.poll.interval.ms` alongside `max.poll.records`.
4. Evaluate broker transaction state expiration and producer cache `maxAge`.
5. Avoid keeping transactions open while waiting on multi-minute retry backoffs.
6. Configure timeouts with sufficient safety margin without masking hung operations.

Increasing timeouts only avoids false timeouts on valid work. It does not solve duplicate producer IDs or group rebalances from membership changes.

## 16. How does Reason.FENCED affect offsets?

In a Kafka consume-process-produce transaction, the container can include consumed offsets in the same transaction as Kafka outputs.

Example:

~~~text
Input:
  orders.input / P0 / offset 99

Transaction T1:
  produce orders.output / key O-1001
  send source offset 100 into transaction

If COMMIT:
  output committed
  group offset 100 committed

If transaction aborts/is fenced before commit:
  T1's output and source offset must not be treated as committed
~~~

**Original record offset 99** differs from **committed offset 100**. Offset 100 indicates the next position the consumer group should read after record 99 succeeded.

If a producer gets fenced, the application should not manually write offset 100 via `consumer.commitSync()` to "unblock" the partition. Doing so can cause the group to skip a record whose output never committed.

When a new consumer receives the partition, it reads from the valid committed offset. Uncommitted records may be reprocessed; this is why idempotency must be maintained for side effects outside Kafka.

## 17. read_committed and output data after fencing

When a transactional listener sends outputs, records may already have been received by the Kafka broker before the transaction commits. If the transaction ultimately aborts, downstream consumers using **read_committed** do not see records belonging to aborted transactions.

~~~text
Transaction T1:
  produce output A
  producer fenced
  transaction does not commit

Downstream read_committed:
  does not see T1's output A as committed
~~~

Consumers using **read_uncommitted** can read records belonging to aborted transactions too. If downstream systems require Kafka transaction semantics, configure:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

Do not infer a transaction aborted merely because application logs showed a timeout at commit time; certain response failures can leave the client unsure of the final state. Verify transaction outcomes and committed data in a controlled manner.

Outside Kafka, if the listener already updated a database or called an HTTP API before getting fenced, those operations may have completed. `read_committed` does not roll back those external side effects.

## 18. FENCED is not a payload error

When a record violates a schema or business rule, the listener may throw an exception classified as retryable/non-retryable and eventually routed to DLT. With FENCED, the cause lies in **producer transactions/consumer lifecycle**, not necessarily record contents.

| Incident type | Commonly suitable handling |
|---|---|
| Un-deserializable payload | ErrorHandlingDeserializer, recovery, or DLT keeping original bytes |
| Business validation failure | Non-retryable classification, DLT, or business workflow |
| Brief downstream timeout | Retry with finite backoff |
| ProducerFencedException | Stop/close old producer, verify ownership and transactional identity, safely recover container |
| Normal rebalance | ConsumerRebalanceListener, revoke/assign, and offset management |

Do not configure a catch-all business error handler to push `ProducerFencedException` to DLT as if the record were invalid. Doing so can mask infrastructure causes and lose atomic offset commit conditions.

If the exact same event consistently causes a business failure after restarts, investigate that event separately. Yet Reason.FENCED does not prove that event was the culprit.

## 19. Distinguishing FENCED from FencedInstanceIdException

The Kafka client has "fenced" concepts at multiple layers. **ProducerFencedException** is a transactional producer error. In consumer groups using static membership, you may encounter **FencedInstanceIdException**, meaning a static group member's identity is no longer valid.

The two cases are not the same:

~~~text
Transactional producer fencing:
  transactional.id / producer epoch
  -> ProducerFencedException
  -> may lead to ConsumerStoppedEvent.Reason.FENCED

Static consumer membership fencing:
  group.instance.id / member identity
  -> FencedInstanceIdException
  -> consumer group membership problem
~~~

Do not apply the same remediation to both without inspecting the actual exception class. Duplicate `transactional.id` requires checking producer factory/prefix; duplicate `group.instance.id` requires checking static member identity and consumer assignments.

**Reason.FENCED as described by Spring Kafka means a fenced producer when stopContainerWhenFenced=true**, not a catch-all label for every Kafka exception containing the word "fenced".

## 20. Concurrency and child containers

A `ConcurrentMessageListenerContainer` typically manages multiple child `KafkaMessageListenerContainer` instances, each with its own consumer thread and partition assignment.

~~~text
Concurrent container: orders-transformer
    |
    +-- child 0: consumer A -> P0, P1
    +-- child 1: consumer B -> P2, P3
    +-- child 2: consumer C -> P4, P5
~~~

If child 1 hits producer fencing, the `ConsumerStoppedEvent` may be attached to that child container. Distinguish **the child's listener ID**, the parent's state, and remaining children to avoid concluding the entire service stopped.

When handling the event:

- Log the specific source container and parent listener ID if available.
- Inspect the actual state of the entire concurrent container before restarting.
- Avoid calling start on overlapping containers from multiple event listeners.
- Do not use a global boolean like `allKafkaConsumersStopped` merely because of one `ConsumerStoppedEvent`.
- Check transactional ID prefix/suffix against the number of producers that may be created as concurrency rises.

Increasing concurrency can increase transactional producer cache demand and error likelihood when transactional ID configurations collide. Yet increasing concurrency itself does not necessarily cause fencing if transaction infrastructure is properly managed.

## 21. Safe restart policy

Upon receiving Reason.FENCED, you can build **controlled recovery**:

~~~text
ConsumerStoppedEvent(reason=FENCED)
        |
        v
Log and alert
        |
        v
Capture listener/container ID, instance ID,
transaction ID prefix, and exception context
        |
        v
Can root cause self-recover?
        |
   +----+----+
   |         |
  Yes       Unclear / No
   |         |
   v         v
Bounded    Keep container stopped,
backoff    investigate collision,
   |       prevent restart loop
   v
Restart via lifecycle manager
   |
   v
Observe group assignment,
offsets, and transaction success
~~~

A restart should only be judged successful once the container truly resumes consuming, receives assignments, and commits transactions normally—not merely because `start()` returned without throwing an exception.

With multiple replicas, coordination is needed to avoid triggering a wave of simultaneous restarts causing a rebalance storm. For repeated errors, cap retries, increase backoff, and alert operators.

A workflow may rely on Kubernetes restart policy or a lifecycle manager inside Spring. Pick the right mechanism to avoid **two systems both restarting** counterproductively.

## 22. Recovering partition state after FENCED

When a container stops, partitions belonging to the consumer may be assigned to another consumer. Any partition-scoped in-memory state must be treated as belonging to the old owner, never continuing to record progress on lost partitions.

Example:

~~~text
Consumer A:
  P2@51 partially processed
  In-memory cache updated
  Kafka transaction not yet committed

FENCED:
  A stops
  P2 moves to B

Consumer B:
  re-reads from valid committed offset
  rebuilds state or processes idempotently
~~~

Do not manually seek the new consumer to the "last seen offset" saved in memory by the old container. That position may include records not yet processed successfully and not yet committed.

If state cannot be rebuilt, the application needs a durable checkpointing mechanism and consistency between checkpoints and Kafka offsets. FENCED is not a moment guaranteed to allow completely flushing local state; processes can lose membership or stop abruptly before cleanup.

## 23. Side effects outside Kafka after fencing

A transactional listener can simultaneously:

- Update a database.
- Call a REST API.
- Deduct inventory.
- Send an email or notification.
- Publish Kafka outputs.

Kafka transactions only protect the Kafka portion participating in that transaction. When a producer is fenced and the Kafka transaction does not commit, external side effects may already have occurred.

~~~text
Attempt 1:
  UPDATE database -> succeeded
  Kafka output -> producer fenced
  Kafka transaction does not commit

Attempt 2:
  Input re-read by another consumer
  UPDATE database -> risk of running twice
~~~

Therefore:

1. Use a stable event ID across all processing attempts.
2. Record processed event markers in the same DB transaction as side effects if deduplication is needed.
3. Use unique constraints/version checks to prevent race conditions.
4. For APIs supporting idempotency keys, pass a stable key.
5. For critical business state + Kafka events, consider transactional outbox/CDC.

Do not confuse Kafka read-process-write exactly-once semantics with exactly-once business effects.

## 24. Logging and metrics to monitor

A Reason.FENCED incident needs enough information to distinguish transactional ID collisions, transaction timeouts, and rebalances:

~~~text
event=consumer_stopped
reason=FENCED
listenerId=orders-transformer-1
instanceId=orders-pod-a
groupId=orders-transformer
transactionIdPrefix=orders-pod-a-tx-
lastInput=orders.input/P2@51
transactionOutcome=failed_or_unknown
action=investigate_before_restart
~~~

This is a custom-designed application structured log; it is not default Spring Kafka output.

Useful metrics:

- `ConsumerStoppedEvent` count by reason and listener.
- FENCED rate per instance/deployment.
- Transaction commit/abort/fencing errors.
- Transaction duration p95/p99.
- Consumer rebalance count/duration.
- Consumer lag per partition.
- Running/stopped listener container counts.
- Restart attempts and restart failures.
- Time from FENCED until consumer resumes committing successfully.
- Producer cache exhaustion or transactional producer initialization errors.

Do not use event ID, offset, or full `transactional.id` as metric labels if they cause high cardinality. Those details belong in access-controlled logs/traces.

## 25. Diagnosing root cause by symptom

| Symptom | Cause to check | Action |
|---|---|---|
| FENCED repeats right after every restart | Duplicate transactional.id across active instances | Check prefix/suffix and pod lifecycle |
| FENCED coincides with scale/deploy | Rebalance or producer identity conflict | Inspect assignments, rollout overlap, and commit failures |
| FENCED after listener takes too long | Transaction timeout or consumer lost membership | Measure transaction duration, DB/API times, and poll interval |
| FENCED after a very long idle period | Transactional identity expiration / stale cached producer | Check broker expiration and producer maxAge |
| Output invisible to downstream | Transaction uncommitted or aborted | Check read_committed, transaction outcome, and offsets |
| Input record reprocessed | Source offset uncommitted due to failed transaction | Protect side effects with idempotency |
| No ConsumerStoppedEvent FENCED despite ProducerFencedException log | stopContainerWhenFenced=false, different context, or event not published | Check container props and event source |
| Pod has FENCED events yet some partitions keep running | Some child containers stopped, others still running | Inspect child/parent container lifecycles |

An investigation workflow:

1. Find `ProducerFencedException` and the exception chain in logs around the same timestamp.
2. Identify the affected listener ID, instance ID, and `transactional.id`/prefix.
3. Check whether the application has multiple replicas using the same prefix.
4. Compare FENCED timing against deployments, rebalances, and consumer restarts.
5. Inspect transaction timeout, `max.poll.interval.ms`, and p99 listener latency.
6. Check the broker transaction coordinator and producer state.
7. Verify the last committed consumed offset.
8. Check Kafka outputs with a `read_committed` downstream consumer.
9. Assess whether external side effects outside Kafka were duplicated or left incomplete.
10. Decide on controlled restart or configuration fix first.

## 26. Example scenario: two pods sharing transactional.id

Suppose two replicas due to a deployment bug share the prefix `orders-tx-`. Each instance creates a transactional producer with suffix `0`:

~~~text
Pod A:
  KafkaProducer(tx.id=orders-tx-0)
  begins transaction T1

Pod B:
  KafkaProducer(tx.id=orders-tx-0)
  initializes new producer

Kafka coordinator:
  identity's producer epoch is updated

Pod A:
  commits T1 -> ProducerFencedException

Container A:
  stopContainerWhenFenced=true
  stops consumer
  emits ConsumerStoppedEvent.Reason.FENCED
~~~

With this setup, enabling immediate auto-restart on Pod A does not solve the conflict: both pods can again compete for the same transactional ID. Fix instance-specific prefix generation, rolling deployment, or producer lifecycle.

After fixing, the new container uses a valid transactional producer and the consumer can re-read uncommitted records from the group offset. If the listener already created database side effects before getting fenced, reprocessing must be idempotent.

## 27. Example scenario: long transaction and rebalance

Suppose consumer A receives an event and opens a transaction, then waits too long on a database lock:

~~~text
00:00  poll orders/P0@500
00:01  begin T1
00:02  call DB and wait for lock
01:10  consumer group rebalance / transaction timeout
01:20  DB returns result
01:21  producer tries to finish T1
01:22  transaction commit failure / fencing
01:23  container stops, reason FENCED if enabled
~~~

Timestamps in the diagram are illustrative. Not every long-running listener produces this exact error sequence.

Mitigations:

- Reduce DB lock wait times and set timeouts on external calls.
- Do not hold a Kafka transaction open waiting on long backoffs.
- Tune `max.poll.records`, transaction timeout, and `max.poll.interval.ms` sensibly.
- Use circuit breakers or fail-fast to roll back quickly when downstream is unavailable.
- Ensure old processes stop executing business side effects after losing ownership.

Do not default to stretching all timeouts to hours. Longer transactions increase coordinator failure risk and delay `read_committed` downstream consumers.

## 28. Example scenario: fenced after long idle

A very-low-traffic application uses a transactional producer cache. The broker may expire `transactional.id` state after an idle duration per configuration. When the old cached producer is reused, epoch/transactional identity errors can appear.

~~~text
Application:
  transactional producer cached
  topic has no records for a long time

Broker:
  transactional.id state expires per config

New record:
  container uses old producer
  transaction hits producer identity error
~~~

In supported Spring Kafka versions, configuring **DefaultKafkaProducerFactory.maxAge** smaller than the broker expiration time can help replace cached producers before they go stale.

Do not periodically send an "empty transaction" just to keep producers alive without evaluating overhead and lifecycle; first check the producer `maxAge` feature and actual root cause.

## 29. Testing Reason.FENCED

Testing should focus on two parts: **fencing actually happens** and **Spring Kafka container emits the corresponding lifecycle event**.

### Test 1: event listener configuration

1. Create a Kafka listener container with `KafkaTransactionManager`.
2. Enable `stopContainerWhenFenced=true`.
3. Register `@EventListener` receiving `ConsumerStoppedEvent`.
4. When a FENCED reason event fires, confirm the observer records the incident for the right listener ID.
5. Confirm code does not manually commit offsets or operate on `KafkaConsumer` after stopping.

Unit tests can mock `ConsumerStoppedEvent` to test the observer, yet do not prove a producer was actually fenced.

### Test 2: two producers sharing transactional.id

1. Use a test Kafka broker such as Testcontainers Kafka.
2. Create producer A with a fixed `transactional.id`.
3. Start a transaction on A.
4. Initialize producer B with the same `transactional.id` to fence A.
5. Have A perform the next transaction operation and observe the fencing error.
6. With a properly configured container, verify `ConsumerStoppedEvent.Reason.FENCED` and stopped state.

Do not let tests use actual production transactional IDs. Fencing errors can surface at send/commit depending on Kafka client, so tests must wait conditionally rather than relying on a single exception throw point.

### Test 3: no infinite auto-restart

1. Simulate consecutive FENCED events.
2. Verify the restart coordinator caps retry attempts and applies backoff.
3. Verify an alert fires if configuration conflicts remain unresolved.
4. Confirm there is no start/stop loop driving infinite CPU and rebalances.

### Test 4: pending offsets and outputs

1. Listener receives input record and sends output in a Kafka transaction.
2. Trigger fencing before transaction commit.
3. Downstream consumer using `read_committed` verifies uncommitted output is invisible.
4. Start a new consumer and verify uncommitted input is re-read.
5. Verify idempotency if the listener touches a database outside Kafka.

### Test 5: graceful shutdown vs FENCED

1. Stop the container normally.
2. Confirm `ConsumerStoppedEvent` has reason `NORMAL`.
3. Trigger real fencing with `stopContainerWhenFenced=true`.
4. Confirm reason `FENCED`, not lumped into `NORMAL`.
5. Verify metrics and alerts distinguish the two scenarios.

### Test 6: concurrency

1. Create a concurrent listener container with multiple child consumers.
2. Trigger fencing on a transactional producer used by one child.
3. Identify which child stopped and which container is the event source.
4. Confirm the lifecycle manager does not mistakenly restart the whole group or loop the same child.
5. Verify partitions are redispatched without data loss.

In integration tests, use condition-based waits with timeouts, cross-checking group committed offsets and downstream `read_committed`. Do not rely solely on logs containing the word "fenced" to assume event/lifecycle behavior is accurate.

## 30. Common misconceptions

**Reason.FENCED is the name of the Kafka producer exception.** Incorrect. It is a reason value in Spring Kafka `ConsumerStoppedEvent`; the underlying exception is `ProducerFencedException` or a corresponding transactional epoch error.

**Every ProducerFencedException guarantees a Reason.FENCED event.** Incorrect. You must check `stopContainerWhenFenced=true`, event lifecycle, and where the exception arose.

**FENCED means the business record was malformed.** Incorrect. Fencing belongs to transaction identity/lifecycle; the payload may be completely valid.

**Every rebalance leads to Reason.FENCED.** Incorrect. Normal rebalances are typically handled via revoke/assign callbacks.

**Restarting the container immediately fixes all fencing errors.** Incorrect. If transaction IDs still collide or timeouts remain unaddressed, restarts will repeat the error.

**You can retry on a fenced producer.** Incorrect. The old producer no longer has authority to execute transactions and must be replaced via lifecycle.

**AfterRollbackProcessor always runs when a producer is fenced.** Incorrect. You cannot blindly seek partitions when ownership may already be lost; Spring Kafka has dedicated fencing logic.

**FENCED is synonymous with FencedInstanceIdException.** Incorrect. One belongs to transactional producer identity, the other to static consumer group membership.

**Kafka transactions roll back SQL updates too.** Incorrect. External databases or APIs must have their own transactions/idempotency.

**Consumer stopping means the whole consumer group stopped.** Not necessarily. Concurrent containers have multiple child consumers and multiple application replicas.

**Increasing transaction.timeout.ms indefinitely prevents fencing.** Incorrect. Timeout is only one possible cause; duplicate `transactional.id` or lost ownership can still occur.

**You can manually commit input offsets after fencing to avoid retries.** Not recommended. Offsets could advance past uncommitted outputs, losing business data.

## 31. Implementation and operations guide

For Spring Kafka applications using Kafka transactions, design the Reason.FENCED policy right when building listeners:

1. Ensure transactional `ProducerFactory` uses a valid `transactionIdPrefix` without collisions across active instances.
2. Configure `KafkaTransactionManager` and transactional listener containers with the right producer factory.
3. Choose `stopContainerWhenFenced` explicitly, understanding the default value of your running version.
4. Register a `ConsumerStoppedEvent` listener to classify NORMAL, FENCED, and other reasons.
5. Record listener/child container ID, group ID, instance ID, transactional ID prefix, and transaction failure context.
6. Do not treat `ProducerFencedException` like a standard business retry error.
7. Do not seek/commit partitions that lost ownership in the producer fencing recovery path.
8. Verify transaction timeout, `max.poll.interval.ms`, and producer cache lifecycle via metrics.
9. Design a bounded restart policy with backoff, restart-loop prevention, and alerts if conflicts remain unresolved.
10. Ensure downstream uses `read_committed` when aborted Kafka outputs must be ignored.
11. Protect all external side effects outside Kafka with event IDs, idempotency, or transactional outboxes.
12. Test real producer fencing, restarts, transaction aborts, offset recovery, and consumer concurrency.

**Reason.FENCED** is a signal showing that a transactional producer suffered fencing severe enough that the Spring Kafka listener container was configured to stop. It helps applications distinguish a transaction-failure stop from a normal stop. Proper handling is not forcing the old producer to keep running, but **restoring valid identity and ownership, letting Kafka preserve committed offsets/outputs, and then restarting the container in a controlled manner**. This lifecycle handling, combined with idempotency and monitoring, enables consumers to recover without trading off data correctness.
