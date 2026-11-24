# Prerequisites for Transactions to Work Properly

Kafka transactions allow a producer to write multiple records and commit or abort them as a single unit. With Spring Kafka, merely calling `KafkaTemplate.executeInTransaction()` or adding `@Transactional` is not enough for the system to function properly. The producer factory must support transactions, brokers must be able to store transaction state, producer identities must be managed properly, topics and ACLs must allow the operations, and consumers must choose the right isolation level.

A transaction may succeed in a local environment yet fail when deployed across multiple brokers or replicas if these prerequisites are not configured consistently. This article focuses on the infrastructure and configuration conditions you must verify before enabling Kafka transactions in a Spring Kafka application.

## 1. The big picture: conditions that must align together

For transactions to operate reliably, check the following layers:

| Layer | Core requirement |
|---|---|
| Kafka cluster | Brokers support transactions, the transaction coordinator is active, and the internal transaction state log has sufficient replicas/ISR |
| Producer | Producer is initialized in transactional mode with a valid `transactional.id` and idempotence |
| Spring Kafka | `ProducerFactory`, `KafkaTemplate`, and transaction manager are wired together properly |
| Topic | Target topics exist, have appropriate replication, and the producer has write permissions |
| Consumer | Uses `read_committed` when only committed records should be visible |
| Security | ACLs permit required producer IDs, topics, consumer groups, and offset operations |
| Timing | `transaction.timeout.ms` does not exceed the broker limit and transactions do not stay open too long |
| Deployment | Transaction IDs do not collide across concurrently active producers |

```text
Spring application
  KafkaTemplate / KafkaTransactionManager
                 |
                 v
       Transactional Producer
                 |
                 v
          Kafka Broker
       +-------------------+
       | Transaction       |
       | Coordinator       |
       +-------------------+
                 |
                 v
       __transaction_state
                 |
                 v
       Output topic partitions
                 |
                 v
       Consumer read_committed
```

Transactions cover only Kafka operations belonging to the same transaction and the same Kafka cluster. They do not automatically turn a database, an HTTP service, or two independent Kafka clusters into a distributed transaction.

## 2. The Kafka cluster must support transactions

Kafka has supported producer transactions since Kafka 0.11.0. Brokers in the cluster must run a compatible version and operate healthily so producers can register transactions, send data, and commit or abort.

When a producer starts a transaction, Kafka selects a transaction coordinator to manage state for its `transactional.id`. The coordinator writes state into the internal `__transaction_state` topic, then coordinates commit/abort and writes transaction markers to the involved partitions.

This means transactions depend on both the brokers receiving records and the broker acting as the transaction coordinator. If the coordinator or internal transaction state log is unavailable, producers may encounter errors when initializing transactions, sending records, or committing.

You do not need to create `__transaction_state` manually. Kafka manages this internal topic. Administrators must configure brokers so the topic has appropriate replication and ISR.

## 3. Configuring replication for the transaction state log

Two key broker configurations are:

| Broker property | Meaning |
|---|---|
| `transaction.state.log.replication.factor` | Replication factor of the internal topic storing transaction state |
| `transaction.state.log.min.isr` | Minimum replicas that must be in-sync to write transaction state |

Production setups typically require multiple brokers to maintain a replication factor of 3 and min ISR of 2:

```properties
transaction.state.log.replication.factor=3
transaction.state.log.min.isr=2
```

Exact values must match the cluster's broker count and fault-tolerance policy. If a cluster has only one broker while the internal topic requires a replication factor of 3, Kafka cannot create enough replicas and transactions may fail to work.

For a single-broker local environment, you can lower both values to 1:

```properties
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
```

This configuration is strictly for learning or local testing. Never lower production replication factor and min ISR to 1 just to get transactions running; that reduces fault tolerance when a broker goes down.

`transaction.state.log.replication.factor` configures the internal transaction topic. It differs from the replication factor of business topics such as `orders.events` or `payments.events`; configure both layers appropriately.

## 4. Business topics also need proper replication and ISR

A healthy transaction state log does not mean business data has adequate durability. Topics receiving transactional records still need a replication factor and `min.insync.replicas` matching data requirements.

Example creating a topic with three replicas:

```bash
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --create --topic orders.events \
  --partitions 6 --replication-factor 3
```

After creating the topic, you can set a topic config requiring at least two replicas in ISR:

```bash
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name orders.events \
  --alter --add-config min.insync.replicas=2
```

`replication.factor` is a topic creation parameter; `min.insync.replicas` is a topic configuration. Transactional producers normally use `acks=all`; with Spring Kafka, do not override producer properties in ways that break idempotence and transaction compatibility. When ISR drops below `min.insync.replicas`, the producer can receive an error instead of writing a copy that falls short of the required durability level.

Before enabling transactions, check:

- Target topics exist or provisioning mechanisms have permission to create them.
- Partition counts suit parallelism and key distribution.
- Replication factor does not exceed the number of brokers able to host replicas.
- `min.insync.replicas` aligns with the replication factor.
- The producer has write permissions on all target topics in the transaction.

A single transaction can write to multiple topics and partitions within the same cluster, yet every target topic must be able to accept records and transaction markers.

## 5. The producer must have a `transactional.id`

An ordinary Kafka producer can send records without opening a transaction. A transactional producer is identified by `transactional.id`. When initializing transactions, the producer calls the transaction initialization protocol to receive a `producerId` and epoch from the coordinator.

`transactional.id` serves two key purposes:

1. Identifies a logical producer across active sessions so brokers can manage transactions.
2. Enables brokers to fence an old producer when a new producer initializes with the same ID, preventing two producers from writing as one logical producer.

In Spring Kafka, applications rarely set each `transactional.id` manually. `DefaultKafkaProducerFactory` takes `transactionIdPrefix` and constructs concrete IDs for producers it manages.

```text
transactionIdPrefix = orders-pod-a-

Producer instance 1 -> orders-pod-a-0
Producer instance 2 -> orders-pod-a-1
Producer instance 3 -> orders-pod-a-2
```

The suffix gives producers created from the same factory distinct transactional IDs. The prefix must be chosen carefully so it does not collide with prefixes of other instances active in the cluster.

## 6. `transaction-id-prefix` must be unique across instances

With Spring Boot, configure the prefix via `spring.kafka.producer.transaction-id-prefix`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${POD_NAME:orders-local}-tx-
```

In Kubernetes environments, `POD_NAME` can be injected from pod metadata. When running multiple replicas, each pod needs a different prefix. Never use the same static string for all instances.

Example:

```text
orders-service-pod-a-tx-
orders-service-pod-b-tx-
orders-service-pod-c-tx-
```

The prefix should be stable across the lifetime of a logical instance so a new startup can fence an old producer with the same identity. At the same time, two instances running in parallel must never use the same prefix. When scaling or replacing pods, ensure instance names remain distinct.

If two applications share a prefix and generate the same transactional ID, the broker can return `ProducerFencedException` to the older producer. This error usually indicates another producer initialized the same transactional ID or the older producer lost epoch ownership.

## 7. Spring Boot must configure a transactional producer

A sample application configuration:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${POD_NAME:orders-local}-orders-tx-
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[transaction.timeout.ms]": 60000
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
```

When `transaction-id-prefix` is present, Spring Boot can configure a transactional `ProducerFactory` and related transaction components depending on the Boot version. If the application defines custom producer factories, templates, or transaction managers, verify those beans share the same factory and proper prefix.

Do not set `transaction-id-prefix` to an empty string or omit it when calling `executeInTransaction()`. `KafkaTemplate` must obtain a transactional producer from `ProducerFactory`; if the factory is not transaction-capable, the template cannot open a transaction and will throw an error at execution time.

## 8. `ProducerFactory`, `KafkaTemplate`, and transaction manager must match

When configuring manually in Java, `DefaultKafkaProducerFactory` must receive a transaction ID prefix. `KafkaTemplate` and `KafkaTransactionManager` must be created from the exact `ProducerFactory` the application intends to use for transactions.

```java
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Configuration
class TransactionalKafkaConfiguration {

    @Bean
    ProducerFactory<String, String> transactionalProducerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

        var factory = new DefaultKafkaProducerFactory<String, String>(properties);
        factory.setTransactionIdPrefix("orders-local-tx-");
        return factory;
    }

    @Bean
    KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> transactionalProducerFactory) {
        return new KafkaTemplate<>(transactionalProducerFactory);
    }

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> transactionalProducerFactory) {
        return new KafkaTransactionManager<>(transactionalProducerFactory);
    }
}
```

The example above shares one factory across the template and transaction manager. If the template sends using factory A while the transaction manager manages factory B, sends may not join the transaction the application expects.

In production, the prefix in the Java example must come from per-instance configuration instead of hardcoding the same value across all replicas.

If an application has multiple independent transactional `ProducerFactory` beans inside the same instance, each factory also needs a distinct prefix so producers do not generate colliding transactional IDs.

## 9. Producer transaction timeout must stay within broker limits

Producer property `transaction.timeout.ms` defines the maximum duration the producer requests for a transaction. Brokers enforce a limit via `transaction.max.timeout.ms`; the producer-requested value must not exceed the broker limit.

Example:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[transaction.timeout.ms]": 60000
```

If the broker allows up to 900000 ms, requesting 60000 ms fits within the limit. These numbers are only examples; read the cluster's actual configuration and pick a timeout aligned with expected processing time.

The transaction timeout must be sufficient for Kafka operations in the transaction, including sending records and committing. Yet overly long timeouts carry a cost: failed transactions can remain open longer, forcing `read_committed` consumers to wait at the Last Stable Offset.

Do not hold a transaction open while waiting on user input, calling slow HTTP services, or doing unrelated work. Prepare data first, then open the transaction and run a short set of Kafka operations.

## 10. Producer transactions require idempotence

Kafka transactions rely on producer IDs and epochs to manage ordering, retries, and fencing. Transactional producers are configured with idempotence; do not disable idempotence or override producer properties in ways that conflict with transaction requirements.

Idempotence prevents duplicates caused by producer request retries within Kafka's guarantee scope. Transactions add commit/abort boundaries across multiple records. The two features are related, yet not synonymous:

| Mechanism | Primary guarantee |
|---|---|
| Idempotent producer | Limits duplicates from retries within the same producer session/sequence |
| Kafka transaction | Commits or aborts a group of transactional records and can coordinate consumer offsets |
| Consumer idempotency | Protects business side effects when the application reprocesses records |

An idempotent producer does not make database updates, emails, or HTTP requests outside Kafka exactly-once. Consumers still need idempotency if business logic has external side effects or may replay records.

## 11. Consumers must use `read_committed` when hiding aborted records is required

A transactional producer can send records before committing. Consumers using `read_uncommitted` can see transactional records that have not committed yet, including records later aborted.

If downstream systems must process only committed data, configure the consumer:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

`read_committed` makes the consumer return only records from committed transactions and stop at the Last Stable Offset (LSO) while an unfinished transaction sits at the front of the partition log. Consequently, transactions held open too long can make consumers appear stalled even as the log end offset advances.

Not every consumer is required to use `read_committed`. Choose based on consistency needs. For consumers serving business data that must accurately reflect commit/abort boundaries, `read_committed` is generally the right choice.

## 12. Consume-transform-produce requires coordinating offsets in the transaction

If an application only sends multiple records, `KafkaTemplate.executeInTransaction()` may suffice. Yet if a consumer reads an input record, processes it, and sends output records while wanting outputs and input progress to commit atomically, you must use a transactional listener container model or Kafka transaction APIs that send offsets into the transaction.

With Spring Kafka, `KafkaTransactionManager` can be attached to the listener container. The container coordinates sending processed record offsets into the transaction alongside output records. When the transaction commits, outputs and input offsets are confirmed together; on abort, the consumer can re-read the input and re-emit outputs in a new transaction.

Prerequisites to check:

- Consumer group has permissions to read the input topic and manage offsets.
- Transactional producer has permissions to write the output topic.
- Transaction manager and listener container use the right producer factory.
- Container manages offset commits transactionally; do not let independent auto-commit break this boundary.
- Downstream consumers use `read_committed` if aborted outputs must be skipped.

`executeInTransaction()` alone has no awareness of the offset of a record being processed by a listener. Never assume a producer-only callback automatically commits consumer offsets.

## 13. ACLs must permit transaction and topic operations

When a cluster enables authorization, the producer needs permissions for both the transactional ID and topics. For consume-transform-produce flows, the consumer group also needs permission to send offsets into transactions.

| Resource | Typically required permission | Used for |
|---|---|---|
| Transactional ID | `WRITE` | Initializing and executing transactions with the transactional ID |
| Output topic | `WRITE` | Writing records to target topics |
| Input topic | `READ` | Consumer reading source records |
| Consumer group | `READ` | Joining the group and sending offsets into transactions per Kafka mechanics |
| Topic/cluster metadata | Describe permission suited to authorizer | Fetching metadata and running clients |

Exact permissions can vary by operation, Kafka version, and authorizer. Grant least-privilege permissions for the exact transactional IDs, topics, and groups the application uses. Never grant cluster-wide wildcards just to avoid authorization errors.

Common errors when ACLs lack permissions:

- `TransactionalIdAuthorizationException`: principal is not authorized for the transactional ID.
- `TopicAuthorizationException`: producer is not authorized to write target topics or consumer is not authorized to read source topics.
- `GroupAuthorizationException`: consumer is not authorized to use the group or corresponding offset operations.

Verify the actual principal Spring Kafka uses, especially when running with SASL/OAUTH or mTLS across environments with differing principal mappings.

## 14. Broker and producer must agree on transaction timeouts

Two sides of timeouts must be distinguished:

| Setting | Where configured | Meaning |
|---|---|---|
| `transaction.timeout.ms` | Producer | Timeout requested by the producer for a transaction |
| `transaction.max.timeout.ms` | Broker | Upper limit accepted by the broker from producers |
| `transaction.state.log.replication.factor` | Broker | Replication factor of the internal transaction state topic |
| `transaction.state.log.min.isr` | Broker | Minimum in-sync replicas for the internal transaction state topic |

If a producer requests a timeout larger than the broker allows, the broker rejects the configuration/transaction initialization. If the timeout is too short, valid transactions that run slightly slow can time out. Measure send and commit durations under realistic load to choose a sensible value.

## 15. Monitoring the transaction coordinator and producer fencing

In production, monitor indicators that transactions cannot start or complete:

| Indicator | Causes to investigate |
|---|---|
| `ProducerFencedException` | Another producer used the same transactional ID or an old epoch was fenced |
| `TransactionalIdAuthorizationException` | Insufficient ACLs on the transactional ID |
| `CoordinatorNotAvailableException` | Transaction coordinator is unavailable or transitioning state |
| `NotCoordinatorException` | Coordinator moved; client must refresh metadata/retry per Kafka mechanics |
| `TimeoutException` on commit | Slow broker/network, overly long transaction, or commit outcome uncertain to caller |
| `InvalidTxnStateException` | Producer invoked an invalid operation for the current transaction state |
| Consumer lag grows while log end offset grows | Long open transaction holding back LSO, or consumer has not read committed data |

Track transaction duration, commit/abort rate, producer error rate, coordinator availability, consumer lag, and age of unfinished transactions. Exact metric names depend on the Kafka client version and metrics system.

If a producer is fenced, do not simply increase retries or timeouts. Check whether transactional ID prefixes collide across pods, two processes run the same logical producer, or an old producer failed to stop properly.

Brokers also manage state retention for inactive transactional IDs via `transactional.id.expiration.ms`. For applications keeping transactional producers pooled for long periods, you can set `DefaultKafkaProducerFactory`'s maximum producer age (`maxAge`) shorter than the broker's ID expiration if your Spring Kafka version supports it. That lets the factory replace old producers before the broker expires the transactional ID.

## 16. How do local and production environments differ?

| Item | Local single broker | Production cluster |
|---|---|---|
| Transaction state log RF | May be set to 1 for learning/testing | Typically multi-replica, e.g. 3 |
| Transaction state log min ISR | May be set to 1 | E.g. 2 when RF=3 |
| Topic replication | 1 may be acceptable locally | Chosen for fault-tolerance requirements |
| Transaction ID prefix | `orders-local-tx-` | Unique per pod/instance |
| ACLs | May be disabled in sandbox | Least-privilege permissions for transactions/topics/groups |
| Monitoring | Basic logs and metrics | Track coordinator, fencing, timeouts, commit/abort, and lag |
| Consumer isolation | Test both modes | `read_committed` for consumers requiring committed-only data |

Do not copy local configuration into production. Local setups often have one broker so replication must be lowered for the internal topic to be created; production must design replication and ISR for fault tolerance.

## 17. Pre-enablement checklist for transactions

Before deploying, confirm in order:

1. The Kafka cluster runs a transaction-capable version and brokers are healthy.
2. Internal `__transaction_state` has a replication factor and min ISR matching the broker count.
3. Business topics exist with appropriate partition counts and replication.
4. Producer factory has a transaction ID prefix configured.
5. Prefixes differ across concurrently active instances.
6. `KafkaTemplate` and `KafkaTransactionManager` use the same `ProducerFactory` when sharing transaction context.
7. `transaction.timeout.ms` does not exceed the broker's `transaction.max.timeout.ms`.
8. Producer is not configured with settings conflicting with idempotence/transactions.
9. ACLs permit transactional IDs, output topics, input topics, and consumer groups.
10. Consumers needing committed-only data are configured with `read_committed`.
11. Consume-transform-produce flows use container/offset coordination properly.
12. Transactions do not wrap blocking work or long HTTP/database calls outside Kafka boundaries.
13. Alerts exist for fencing, coordinator errors, transaction timeouts, abort rates, and consumer lag.
14. Integration tests verify commit, abort, `read_committed`, ACLs, and multiple instances.

## 18. Common misconceptions

1. **Configuring `transaction-id-prefix` alone is enough.** Brokers still need a working transaction coordinator and writable internal transaction state log.
2. **Using replication factor 3 on a single-broker cluster.** The internal topic cannot allocate enough replicas; local environments need dedicated settings.
3. **Using the same prefix across all pods.** Producers can fence each other due to colliding transactional IDs.
4. **Confusing the transaction state log with business topics.** It is an internal broker topic with its own replication settings.
5. **Assuming all consumers hide aborted records automatically.** Only `read_committed` consumers filter uncommitted/aborted transactional records.
6. **Setting arbitrarily huge transaction timeouts.** Producers cannot exceed broker limits; long timeouts also keep transactions open and hold back the LSO.
7. **Using two different `ProducerFactory` beans for the template and transaction manager.** Sends may fail to join the managed transaction.
8. **Overlooking transactional ID ACLs.** Topic write permission does not necessarily grant permission to initialize transactions.
9. **Assuming Kafka transactions cover databases.** Kafka transactions cover only properly enlisted Kafka resources.
10. **Testing only with mocks.** Mocks do not verify coordinator behavior, commit markers, abort markers, fencing, or broker isolation semantics.

Transactions work reliably only when brokers, producers, Spring Kafka, topics, ACLs, and consumers all meet compatible prerequisites. Verify the transaction state log and coordinator on the cluster, assign distinct transactional ID prefixes per instance, wire `KafkaTemplate` with the right `ProducerFactory`, bound timeouts within broker limits, and use `read_committed` on consumers requiring committed data. Only once these prerequisites are verified through integration tests and monitoring do transactions become a dependable foundation for production messaging flows.
