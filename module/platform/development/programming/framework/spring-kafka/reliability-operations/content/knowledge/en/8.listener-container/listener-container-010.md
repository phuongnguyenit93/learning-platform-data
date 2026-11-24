# stopContainerWhenFenced

In Spring Kafka, `stopContainerWhenFenced` is a listener container property used to stop the container when a transactional producer is fenced by Kafka and throws `ProducerFencedException`. Fencing occurs when the broker determines an old producer no longer has permission to use the same `transactional.id`, typically because another producer initialized with that identifier and received a newer producer epoch.

Once a producer is fenced, the old producer can no longer validly complete transactions. If the listener container keeps receiving records and trying to open transactions with the invalidated producer, subsequent processing attempts will continue failing. Enabling `stopContainerWhenFenced` causes the container to stop so the system detects the incident and resolves the root cause before letting the consumer continue.

## 1. What is producer fencing?

Kafka uses `transactional.id` to identify a transactional producer across restarts. When a producer initializes transactions via `initTransactions()`, the broker tracks a producer epoch bound to that transactional ID. The epoch helps the broker distinguish the current producer from a stale producer that may still be running due to restarts, network partitions, or orchestration glitches.

Suppose producer A is using `transactional.id=orders-instance-1`. Later, producer B initializes with the same transactional ID. The broker issues a new epoch to B and fences A. Subsequent transactional operations by A can fail with `ProducerFencedException` because A has become a stale producer.

```text
Producer A initializes transactional.id=orders-1
        |
        v
Broker assigns producer epoch to A
        |
        v
Producer B initializes same transactional.id=orders-1
        |
        v
Broker issues new epoch to B and fences A
        |
        +------------------------------+
        |                              |
        v                              v
Producer B continues             Producer A is fenced
with new epoch                   transaction operations fail
```

Fencing is a safeguard for transaction correctness. It prevents a stale producer from continuing to write data after a newer producer has taken over the same transactional identity. Therefore, `ProducerFencedException` signals that the current producer has lost ownership of the transactional ID, not a transient network error solvable by retrying the same operation on the same producer.

## 2. Why should the listener container stop when fenced?

With a transactional listener container, Spring Kafka starts a Kafka transaction for listener processing as configured. Record listeners usually process each record in its own transaction; batch listeners process a batch in a transaction. When the listener completes, the container commits the transaction. If the listener throws an exception or the transaction fails, the container executes rollback and error handling as configured.

If the producer used in the transaction is fenced, the container cannot use that producer to commit transactions. `stopContainerWhenFenced=true` instructs the listener container to stop upon receiving `ProducerFencedException`. Stopping prevents the container from continuing to poll and process further records while its transactional producer is no longer valid.

Example flow:

```text
Listener container begins transaction
        |
        v
Listener processes record or batch
        |
        v
Producer sends transactional data / commits transaction
        |
        v
Broker detects stale producer epoch
        |
        v
ProducerFencedException
        |
        v
stopContainerWhenFenced=true
        |
        v
Listener container stops
```

This is listener container-level behavior. It does not necessarily stop the entire JVM, pod, or other listener containers in the application. An application can have multiple listener endpoints; monitor which specific container stopped and the status of remaining endpoints.

This property is especially helpful when using transactional producers to implement exactly-once semantics for Kafka-to-Kafka streams. When a producer is fenced, stopping the container surfaces the incident clearly in operations instead of continuing to run with an invalidated producer.

## 3. Configuring stopContainerWhenFenced

The property is configured on the listener container factory's `ContainerProperties`. Example:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                KafkaAwareTransactionManager<String, Object> transactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);

    ContainerProperties container = factory.getContainerProperties();
    container.setKafkaAwareTransactionManager(transactionManager);
    container.setStopContainerWhenFenced(true);

    return factory;
}
```

`KafkaAwareTransactionManager` in the example is a Kafka transaction manager configured with a transactional `ProducerFactory`. If the application already attaches a transaction manager to the factory, simply set the property:

```java
factory.getContainerProperties().setStopContainerWhenFenced(true);
```

Listener endpoint using that factory:

```java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    containerFactory = "kafkaListenerContainerFactory"
)
public void consume(OrderCreated event) {
    orderService.handle(event);
}
```

Ensure the listener container actually runs with a transaction manager and transactional producer factory. Setting `stopContainerWhenFenced` alone does not turn a regular listener into a transactional listener and does not create a `transactional.id`.

## 4. Transactional producers require proper transactional.id

Spring Kafka supports transactional producers via `DefaultKafkaProducerFactory` with `transactionIdPrefix`. The factory generates transactional IDs from the prefix and factory-managed suffixes. The prefix must distinguish concurrently running application instances so independent instances do not accidentally share the same transactional ID.

Example creating a producer factory:

```java
DefaultKafkaProducerFactory<String, Object> producerFactory =
        new DefaultKafkaProducerFactory<>(producerProperties);

// appInstanceId must be unique across active instances.
producerFactory.setTransactionIdPrefix(appInstanceId + "-orders-");
```

With Spring Boot, the transactional prefix can be declared via the corresponding producer property for your Boot version:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${APP_INSTANCE_ID}-orders-
```

`APP_INSTANCE_ID` must have a value appropriate for the deployment model. Do not assign the same static prefix to multiple concurrently running replicas if they share brokers and can produce identical transactional IDs. When two instances create producers with the same transactional ID, the later-initializing instance can fence the other instance's producer.

On the other hand, transactional ID also serves to recognize an old producer when an instance restarts. Reusing the same logical instance's identity allows a new producer to fence a lingering old producer. Therefore, design identities around deployment lifecycle: unique across concurrently active instances, yet appropriately stable for the system's restart and fencing strategy.

With `DefaultKafkaProducerFactory`, suffixes are managed to create transactional producers for threads or containers. Do not append arbitrary suffixes in multiple places without understanding the factory's caching and producer management; let the factory manage suffixes or use Spring Kafka configuration supported for your application version.

## 5. stopContainerWhenFenced is not a retry mechanism

When a container stops because its producer was fenced, `stopContainerWhenFenced` does not fix the transactional ID, recreate the transaction manager, or guarantee automatic container restart. It is a container lifecycle protection action taken upon detecting that the producer lost authority.

Follow these remediation steps in order:

1. Identify which listener container stopped and capture the root exception.
2. Find the other producer or application instance using the same transactional ID.
3. Check `transactionIdPrefix`, suffix generation, replica count, and concurrency.
4. Confirm the stale producer has stopped or eliminate the source of conflict.
5. Ensure the producer factory can create valid transactional producers.
6. Restart the listener container only after the fencing cause has been resolved.

If you merely restart the container while another instance still uses the same transactional ID, the new producer may immediately be fenced again. The system will repeat a cycle of start, receive record, transaction failure, and stop. Resolve the conflict cause before recovering.

## 6. Distinguishing producer fencing from other errors

Not every error related to consumer groups or transactions is `ProducerFencedException`.

| Error or scenario | Meaning | Handling direction |
|---|---|---|
| `ProducerFencedException` | Transactional producer lost permission to use transactional ID due to a newer producer epoch. | Check transactional ID conflict and stop container per configuration. |
| `InvalidProducerEpochException` | Producer epoch is invalid for the attempted operation. | Check producer state, transaction, and why the epoch changed. |
| `FencedInstanceIdException` | Consumer static member ID conflicted in the group. | Check `group.instance.id` and consumer member identities. |
| `CommitFailedException` | Consumer cannot commit offsets, typically due to changed group membership or partition ownership. | Check rebalances, poll loop, and group state. |
| Transaction timeout or transient broker error | Transaction did not complete in time or broker/network encountered an issue. | Check timeouts, brokers, connectivity, and retry/error handling. |

`stopContainerWhenFenced` focuses on transactional producer fencing. Do not use it as a catch-all switch for consumer errors, commit errors, or other transaction errors.

## 7. Relationship with rollback and error handlers

In a transactional listener, exceptions during processing usually cause the transaction to roll back. Spring Kafka can use `AfterRollbackProcessor` to handle records after rollback, such as seeking to re-read or recovering records after a number of attempts. With a fenced transactional producer, the producer is no longer valid for subsequent transactional operations.

Therefore, upon receiving `ProducerFencedException`, stopping the container means something different from retrying an ordinary business record error. Retrying may fit when a database is temporarily unavailable or a processing error is recoverable; fencing means the producer identity has been superseded. Continuing to use the old producer will not resolve the condition.

If the application has a dead-letter topic or recovery pipeline, distinguish record errors from transactional producer infrastructure errors. Do not route a record to a dead-letter topic simply because the producer was fenced if publishing to the dead-letter topic also depends on the invalidated transactional producer. First restore valid transactional capability, then let error handling run per policy.

## 8. Monitoring stopped listener containers

Applications need to observe listener container states and capture stop reasons. You can use `KafkaListenerEndpointRegistry` to look up a container by ID and check its state:

```java
@Component
public class ListenerContainerStatus {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerContainerStatus(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isOrdersListenerRunning() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        return container != null && container.isRunning();
    }
}
```

The code above illustrates querying state, not capturing the stop reason. In operations, log the fencing exception along with application instance ID, transactional ID/prefix, listener ID, and timestamp. When multiple child containers exist, pinpoint which container was affected and the state of remaining consumers.

Spring Kafka emits application events related to consumer and container lifecycle. You can register listeners for events supported by your version to record when consumers stop, start, or containers change state. Verify event names and metadata in your specific Spring Kafka version; do not guess root causes solely from a generic stop event.

Useful metrics include:

- Count of `ProducerFencedException` per listener and application instance.
- Number of running and stopped listener containers.
- Container restart counts after fencing incidents.
- Consumer lag and container downtime.
- Transaction abort/commit failure counts and related producer errors.
- Number of replicas running with the same transactional ID prefix or duplicate instance ID configuration.

## 9. Controlled container recovery

After fixing the root cause, the listener container can be restarted through the registry. Example:

```java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null && !container.isRunning()) {
    container.start();
}
```

Call `start()` only after valid transactional producers can be created and transactional ID conflicts are resolved. Restarting too early can make the container hit the exact same fencing error on the next transaction.

In production, recovery can be performed by an operator or a controlled orchestrator workflow. If auto-restarting, include backoff, attempt limits, alert metrics, and confirmation that the cause is gone. Avoid unbounded fast restart loops because they increase rebalances, log noise, and broker load.

## 10. Deployment scenarios prone to fencing

### Multiple replicas using the same transactional prefix

If two replicas use the same `transactionIdPrefix` and the factory generates the same transactional ID suffixes, one replica's producer can fence the other's. This is a common misconfiguration when scaling a transactional app from one instance to multiple replicas while keeping a fixed prefix.

The fix is giving each active instance a unique prefix and checking how suffixes are generated. Do not use a shared environment name like `orders-` as the prefix across pods running concurrently.

### Restart while old instance has not fully stopped

In some rollout or network partition scenarios, a new instance may start before the old producer truly finishes. If both instances share the same identity, the new producer fences the old producer. Fencing protects transaction correctness, yet the old instance's container needs to stop and the system must ensure which instance is authorized to continue.

### Concurrency and producer factory

A listener container can have multiple consumer threads when using concurrency. Spring Kafka's transactional producer factory manages producers and suffixes through its own mechanism. Let the factory generate proper transactional IDs for each producer; avoid manually reusing a non-thread-safe transactional producer or assigning the same transactional ID to concurrent producers.

### Confusing static member ID

`group.instance.id` belongs to consumer group membership, whereas `transactional.id` belongs to producer transactions. These two identifiers serve different mechanisms. Duplicate `group.instance.id` can trigger consumer static member fencing; duplicate `transactional.id` can fence producers. Check the exact exception type before adjusting configuration.

## 11. Operational checklist when ProducerFencedException occurs

1. Capture the root exception and confirm it is `ProducerFencedException`.
2. Record listener ID, application instance, transactional ID/prefix, and error timestamp.
3. Check replica count, rollouts, and concurrency at the time of fencing.
4. Identify whether another producer is initializing with the same transactional ID.
5. Verify `transactionIdPrefix` is unique across active instances.
6. Check `DefaultKafkaProducerFactory` configuration and how suffixes are managed.
7. Confirm the listener container stopped if `stopContainerWhenFenced=true`.
8. Resolve the conflicting instance or configuration before restarting the container.
9. Monitor transaction commits/aborts, container state, consumer lag, and rebalances after recovery.
10. Verify potentially redelivered records are processed idempotently.

## 12. Usage guidelines

- Enable `stopContainerWhenFenced` on transactional listener containers when you want the container to stop immediately if its producer is fenced.
- Configure the transaction manager and transactional producer properly; this property does not enable transactions by itself.
- Ensure transactional ID/prefix values do not collide across concurrently active application instances.
- Understand fencing as a sign that an old producer lost authority, not a transient error to retry endlessly on the same producer.
- Distinguish `ProducerFencedException` from consumer static membership errors, offset commit errors, and other transaction errors.
- Monitor container state and exceptions to detect stopped listeners.
- Restart only after resolving the conflict; use backoff and limits if automating recovery.
- Design business logic idempotently to tolerate redelivered records after rollbacks, restarts, or rebalances.

`stopContainerWhenFenced` lets Spring Kafka stop a listener container when its transactional producer has been fenced by Kafka. Paired with unique transactional ID configuration, container monitoring, and controlled recovery, applications can surface producer conflicts early and avoid continuing to process with a producer that can no longer commit transactions.
