# `transactional.id` and `transactionIdPrefix`

Kafka transactions allow a producer to write multiple records as an atomic unit: consumers using the appropriate read mode will see either the entire committed transaction or none of the records from an aborted transaction. To manage transaction state and detect when an old producer has been replaced, Kafka attaches an identifier to the producer called `transactional.id`.

When using Spring Kafka, applications typically configure `transactionIdPrefix` on the producer factory. Spring Kafka combines this prefix with a factory-managed suffix to construct the actual `transactional.id` for each transactional producer. Therefore, the prefix must be designed per running application instance; if multiple instances share the same prefix, producers can fence each other and cause transactions to fail.

## 1. Distinguishing the two concepts

The two names look similar, yet they belong to different layers:

| Concept | Where used | Role |
|---|---|---|
| `transactional.id` | Kafka producer configuration | Identifier of a transactional producer in Kafka. Kafka uses it to track transactions, recover state, and fence an old producer when a new producer claims the same ID. |
| `transactionIdPrefix` | Spring Kafka `DefaultKafkaProducerFactory` and Spring Boot configuration | Prefix used by Spring Kafka to generate distinct `transactional.id` values for the producers managed by that factory. |

For example, an application sets the prefix to `orders-pod-a-`. Spring Kafka can generate IDs such as `orders-pod-a-0`, `orders-pod-a-1` for transactional producers issued by the factory. The specific suffix is managed by the factory; the application should not hardcode a fixed suffix and share it across multiple active producers.

In raw Kafka configuration, the exact property is `transactional.id` (ending with *al* in `transactional`). Spring Kafka provides `transactionIdPrefix` to manage this range of IDs. Do not confuse it with `transaction.id`, which is not a Kafka producer configuration property.

## 2. What does Kafka use `transactional.id` for?

A Kafka transaction can include multiple records, including records sent to multiple partitions or topics in the same cluster. The producer begins a transaction, sends records, and then commits or aborts. Consumers configured with `isolation.level=read_committed` read only records belonging to committed transactions; records belonging to ongoing or aborted transactions are not returned as committed data.

`transactional.id` helps brokers recognize a logical producer across sessions. When a new producer initializes with the same ID, the broker increments the producer epoch and fences the old producer. The old producer no longer has permission to continue writing transactions with that ID. This mechanism prevents two producers from owning the same transactional identity simultaneously and enables transaction state recovery after a producer restarts.

`transactional.id` also enables the guarantees required for producer transactions and implies idempotence. However, it is important to distinguish:

- **Idempotent producer** limits duplicate records caused by producer send retries within a single producer session.
- **Transactions** allow committing or aborting a group of records as one unit and can coordinate consumer offsets within the same Kafka transaction.
- **Exactly-once processing in Kafka** requires coordinating producer transactions, consumer offsets, and `read_committed` consumers in the right pattern. It does not automatically turn database updates or HTTP calls into exactly-once operations.

`transactional.id` is an identifier for managing producer transactions—not an event ID, consumer group ID, or business transaction name.

## 3. Spring Kafka generates `transactional.id` from the prefix

`DefaultKafkaProducerFactory` can manage transactional producers and assign a distinct suffix to each producer. The application configures the prefix on the factory; the factory is responsible for issuing producers with complete IDs and reusing producers according to its caching mechanism.

In Spring Boot, you can enable transactions with the `spring.kafka.producer.transaction-id-prefix` property:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      transaction-id-prefix: ${KAFKA_INSTANCE_ID:local}-orders-
```

`KAFKA_INSTANCE_ID` must represent the running instance. For instance, each Kubernetes pod can use its pod name as the value. When running multiple local processes, supply a different value to each process; the default `local` is only appropriate when a single instance uses that prefix.

If creating `DefaultKafkaProducerFactory` manually, configure the prefix in Java:

```java
@Bean
public ProducerFactory<String, OrderEvent> orderProducerFactory(
        @Value("${app.kafka.instance-id}") String instanceId) {

    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JsonSerializer.class);

    DefaultKafkaProducerFactory<String, OrderEvent> factory =
            new DefaultKafkaProducerFactory<>(props);
    factory.setTransactionIdPrefix("orders-" + instanceId + "-");
    return factory;
}
```

This is a minimal configuration example; real applications should obtain bootstrap servers, serializers, security settings, and producer properties from environment configuration. When Spring Kafka manages transactional IDs via a prefix, do not also set a static `transactional.id` in the producer properties map, because the factory needs to generate suffixed IDs itself.

If using Spring Boot auto-configuration, set the prefix at `spring.kafka.producer.transaction-id-prefix`. If creating the producer factory manually, call `setTransactionIdPrefix(...)`. Choose one clear configuration place so a custom producer factory does not inadvertently ignore the prefix declared in Boot properties.

## 4. The prefix must be unique across active instances

This is the most important operational rule: application instances running concurrently and creating transactional producers must have distinct prefixes. Never use a fixed prefix based solely on the service name across all replicas.

Suppose there are three replicas of `order-service`:

| Instance | Suitable prefix | Example transactional IDs |
|---|---|---|
| Pod A | `orders-pod-a-` | `orders-pod-a-0`, `orders-pod-a-1` |
| Pod B | `orders-pod-b-` | `orders-pod-b-0`, `orders-pod-b-1` |
| Pod C | `orders-pod-c-` | `orders-pod-c-0`, `orders-pod-c-1` |

If all three pods use `orders-`, the factories may generate the same ID range, such as `orders-0`. When one producer initializes with an ID currently in use by another producer, Kafka fences the old producer. Consequences can include `ProducerFencedException`, aborted transactions, send failures, or listener containers entering error recovery.

Example of a conflict-prone configuration:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-
```

The prefix above is only safe if strictly one instance uses it within the same Kafka scope. When scaling to multiple replicas, include an instance ID in the prefix:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${HOSTNAME}-orders-
```

In Kubernetes, `HOSTNAME` is typically the pod name and differs across pods. In other environments, use a platform-provided instance ID. Never share an identical environment variable value across all replicas.

The prefix must be unique across any producer factories capable of generating overlapping IDs in the same cluster. If a single application has multiple independent transactional producer factories, differentiate by service, instance, and factory role, such as `orders-pod-a-outbound-` and `orders-pod-a-audit-`.

## 5. Unique and stable: how to choose an instance ID?

The prefix must distinguish concurrently active instances. At the same time, a stable identifier for the same logical instance can help Kafka fence the old process when a new process replaces it.

| Instance ID source | Characteristics | Notes |
|---|---|---|
| Pod or task name | Typically unique across running replicas and stable for the pod/task lifetime | Fits orchestrated environments; rolling deployments must ensure old and new pods have different names while both are active. |
| Hostname combined with service | Easy to operate on VMs or servers | If multiple processes of the same service run on one host, add a process slot or separate instance ID. |
| Startup-generated UUID | Easy to produce a distinct value per process | Reduces ID collision risk, but cannot automatically fence an old process if it is still alive with its previous UUID. |
| Fixed service name | Easy to configure | Unsuitable for multiple replicas because all may generate the same range of transactional IDs. |

In rolling-update deployments, each new instance must have a distinct prefix from any old instance still running. When the same logical instance restarts and reuses its identifier, the new producer can fence the old producer that held the same ID. This is useful behavior to prevent two processes from owning the same producer identity, which also means two concurrent processes must never share a prefix.

Avoid picking a fresh random value on every startup if the system needs to recognize and fence an old producer of the same logical instance. A UUID can guarantee concurrent uniqueness, yet a stable per-instance identifier generally makes lifecycle and split-brain troubleshooting easier.

## 6. A prefix does not automatically turn every operation into a transaction

Declaring `transactionIdPrefix` enables Spring Kafka to create transactional producers. For a group of operations to actually run inside a transaction, the application must still execute them within a transaction boundary, such as via `KafkaTemplate.executeInTransaction(...)` or `KafkaTransactionManager`.

Example using `executeInTransaction`:

```java
public void publishOrderEvents(OrderCreated created, OrderAudited audited) {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders", created.orderId(), created);
        operations.send("order-audit", audited.orderId(), audited);
        return null;
    });
}
```

Both records are sent in the same transaction opened by `executeInTransaction`. If the callback completes normally, the transaction commits; if an exception escapes the callback, the transaction aborts. The topics must belong to the same Kafka cluster, and the `KafkaTemplate`'s producer factory must be configured as transactional.

You can use `KafkaTransactionManager` when integrating transactions into Spring's transaction abstraction:

```java
@Bean
public KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
        ProducerFactory<String, OrderEvent> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
```

Then a Spring method can use `@Transactional("kafkaTransactionManager")` to send records via `KafkaTemplate` within a transaction. The method must be invoked through the Spring proxy; self-invocation within the same bean does not trigger the transaction proxy as expected. When combining Kafka with database transactions, clearly understand which transaction manager manages which resource and the commit order; two systems do not automatically become an atomic distributed transaction merely by using `@Transactional`.

With `@KafkaListener`, you can configure the listener container to use `KafkaTransactionManager` to handle consume-transform-produce in a transaction. Consumed record offsets and published records can then be committed in the same Kafka transaction. The API for configuring the container transaction manager may vary across Spring Kafka versions; use the API matching your project's version.

## 7. Producer fencing and common errors

`ProducerFencedException` usually indicates that another producer has claimed the same transactional ID or the current producer no longer has a valid epoch. When encountering this error, do not merely increase timeouts or retry infinitely; inspect the prefix source and instance lifecycle.

| Symptom | Possible cause | What to check |
|---|---|---|
| `ProducerFencedException` | Two producers share a transactional ID; old producer was fenced by new producer | Check `transactionIdPrefix`, instance ID, replica count, and producer factories. |
| Transactions repeatedly abort during deployment | New and old instances share the same prefix during rolling update | Ensure each running instance has a distinct prefix. |
| Transactions are not enabled | Producer factory has no prefix or `KafkaTemplate` uses a different factory | Check bean wiring and Boot/custom factory configuration. |
| Cannot read uncommitted records | Consumer uses `read_committed` and producer has not committed or aborted the transaction | Check transaction status, producer logs, and transaction timeout. |
| Transaction timeout | Work inside transaction takes too long or timeout configuration is inappropriate | Shorten transaction work, check `transaction.timeout.ms` and broker limits. |
| Producer factory runs out of available transactional producers | Concurrent producer demand exceeds configured cache/suffix capacity | Check concurrency, cache capacity, and producer lifecycle for your Spring Kafka version. |

Kafka can fence an old producer when the same ID is re-initialized. A fenced producer cannot continue transactions with that ID; the application must let the producer factory/container create or obtain a valid producer according to Spring Kafka's mechanism. Do not catch `ProducerFencedException` and treat the old transaction as successful.

## 8. Related configurations that do not replace the prefix

Several properties frequently appear alongside transactions, yet solve different problems:

| Property | Meaning | Relationship to `transactionIdPrefix` |
|---|---|---|
| `transaction.timeout.ms` | Maximum time the broker allows a transaction to remain open before timing out | Does not generate IDs; adjusts the transaction duration limit. |
| `transaction.max.timeout.ms` | Maximum timeout limit the broker accepts from producers | Upper bound for `transaction.timeout.ms`, not a prefix. |
| `isolation.level` | Consumer choice between `read_uncommitted` and `read_committed` | Determines whether consumers see uncommitted/aborted records. |
| `enable.idempotence` | Ensures producer send retries do not create duplicates within the producer's supported scope | Transactional producers enable the required idempotence guarantees; this property does not replace a unique ID. |
| `group.id` | Consumer group identifier | Not used as a transactional ID; many producers may be unrelated to that group. |

The broker cluster must also configure the transaction state log with sufficient durability for the operational environment. In production, verify replication factor and min ISR suitable for the broker count, topic ACLs/permissions, and transaction timeout limits. A correct `transactionIdPrefix` cannot compensate for an under-replicated broker transaction state log.

## 9. Checklist for validating configuration in a real environment

Before deploying transactional producers, verify step by step:

1. **Identify producer scope.** List services, instances, producer factories, and the role of each factory creating transactional producers.
2. **Design the prefix.** Combine service name, instance ID, and factory role. Confirm no two concurrent instances use the same prefix in the same cluster.
3. **Verify ID generation.** If using Spring Boot, verify `spring.kafka.producer.transaction-id-prefix` binds properly. If creating factories manually, verify `setTransactionIdPrefix(...)` is called on the exact factory used by `KafkaTemplate`.
4. **Verify transaction boundaries.** Confirm record sends occur within `executeInTransaction`, `@Transactional` with `KafkaTransactionManager`, or a properly configured transactional listener container.
5. **Verify consumer visibility.** For pipelines that must read only committed data, set `isolation.level=read_committed` on the corresponding consumers.
6. **Test multiple instances.** Start at least two instances simultaneously, verify generated transactional IDs differ, and confirm no unexpected fencing occurs.
7. **Test restarts and rolling updates.** Verify a new instance does not collide with any other running instance's prefix; verify a replacing logical instance properly fences its old process.
8. **Test commit and abort.** Send multiple records in one transaction and verify a `read_committed` consumer sees the committed batch and never sees aborted records.
9. **Monitor production.** Collect transaction commit/abort counts, timeouts, producer fencing, send errors, and transaction duration. Alert when unexpected fencing occurs.

In operational logs, record service name, instance ID, producer factory role, and transaction outcome. Prefixes are not secrets, yet avoid logging unnecessary configuration details. When fencing incidents happen, this information helps identify which two instances are contending for the same ID.

`transactional.id` is the Kafka identifier used to manage a transactional producer; `transactionIdPrefix` is how Spring Kafka systematically constructs those identifiers. When each instance has a distinct prefix, the producer factory manages suffixes, and transaction boundaries are clearly configured, applications can use Kafka transactions more safely in multi-replica environments and during rolling updates.
