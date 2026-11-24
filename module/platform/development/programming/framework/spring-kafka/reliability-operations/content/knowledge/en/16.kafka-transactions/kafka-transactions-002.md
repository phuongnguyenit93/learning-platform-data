# transactionIdPrefix

In Spring Kafka, **`transactionIdPrefix`** is the prefix used by `DefaultKafkaProducerFactory` to assign a `transactional.id` to Kafka producers capable of executing transactions. This is an essential configuration for applications that need to write multiple records to Kafka as an atomic unit or write output records and commit input offsets within the same Kafka transaction.

`transactionIdPrefix` is not just a label for logs. From this prefix, Spring Kafka generates transactional producer identifiers; the Kafka transaction coordinator uses them to manage producer IDs, epochs, and detect stale or duplicate producer identities. If multiple instances end up using the same effective `transactional.id`, they can **fence** each other, causing aborts, listener errors, retries, and consumer lag.

This lesson focuses on how to configure and manage prefixes properly in multi-replica systems, how they integrate with Spring Boot and Kafka listener transactions, the limits of Kafka's exactly-once semantics, and common operational scenarios.

## 1. Distinguishing transactionIdPrefix and transactional.id

A raw Kafka producer uses the `transactional.id` configuration. Spring Kafka allows declaring `transactionIdPrefix` on the producer factory; the factory combines this prefix with a factory-managed suffix to build the full `transactional.id` for each transactional producer.

Example of a service with three instances:

~~~text
Deployment        : orders-service
Environment       : production

Instance 0:
  transactionIdPrefix = prod-orders-0-tx-
  transactional.id    = prod-orders-0-tx-<suffix>

Instance 1:
  transactionIdPrefix = prod-orders-1-tx-
  transactional.id    = prod-orders-1-tx-<suffix>

Instance 2:
  transactionIdPrefix = prod-orders-2-tx-
  transactional.id    = prod-orders-2-tx-<suffix>
~~~

The `<suffix>` shown here is purely illustrative; suffix format and lifecycle vary by Spring Kafka version and producer factory strategy. Do not write code that assumes suffixes always start at 0 or always map to a specific partition.

| Identifier | Managed by | Role |
|---|---|---|
| `transactionIdPrefix` | Application / Spring Kafka producer factory | Creates a namespace for an instance's transactional producers. |
| `transactional.id` | Kafka producer, built by the factory from prefix and suffix | Identity used with the Kafka transaction coordinator. |
| Producer ID and epoch | Kafka broker and producer protocol | Tracks producer generation, fences stale producers, and ensures transaction correctness. |
| `client.id` | Kafka client | Used for logs, metrics, and quotas; does not replace transactional ID. |
| `group.id` | Kafka consumer | Identifies consumer group and offsets; not a producer transaction ID. |
| `group.instance.id` | Static consumer member | Preserves consumer identity across restarts, independent of producer prefix. |

**Rule:** two producers that may run concurrently to process independent transactions must never share the same effective `transactional.id`. Identifiers must be isolated across application instances, producer factories, or any producer source that could generate colliding suffixes.

## 2. Why Does Kafka Need a Stable Transactional ID?

A Kafka transaction can span multiple `send()` calls across multiple partitions/topics. The producer begins a transaction, sends records, and then commits or aborts. The Kafka coordinator binds transaction state to `transactional.id`; when a new producer initializes with the same ID, the broker can issue a new producer epoch and **fence** the producer from the older generation.

~~~mermaid
sequenceDiagram
    participant F as Spring Kafka ProducerFactory
    participant P as Transactional KafkaProducer
    participant C as Transaction Coordinator
    participant T as Kafka output topics
    F->>P: Provide producer with transactional.id
    P->>C: initTransactions
    C-->>P: Valid producerId and epoch
    P->>C: beginTransaction
    P->>T: send A
    P->>T: send B
    alt Processing succeeds
        P->>C: commitTransaction
        C-->>P: Commit succeeded
    else Processing fails
        P->>C: abortTransaction
        C-->>P: Transaction aborted
    end
~~~

Fencing prevents an old producer from continuing to write once another producer has become the owner of that transactional ID. This is useful when an instance restarts while the old process is still alive or stuck on the network.

However, if two valid replicas are configured with the same prefix and their factories generate the same suffix, the broker cannot tell they represent independent workloads. They may repeatedly initialize the same transactional ID and fence one another. `ProducerFencedException` or producer-epoch errors should be treated as signals to investigate identity/lifecycle rather than mere network timeouts.

### Kafka transactions vs idempotent producers

An idempotent producer reduces duplicates caused by write retries from a single producer session. Kafka transactions add commit/abort boundaries across multiple records and can include consumer offsets in the same transaction in a consume–transform–produce flow.

`transactionIdPrefix` is the component that supplies identity to Spring Kafka's transactional producers. It does not automatically enable transactions on every `send()` call and does not replace proper configuration of the transaction manager or container.

## 3. Configuration with Spring Boot

Spring Boot provides the `spring.kafka.producer.transaction-id-prefix` property:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.internal:9092
    producer:
      transaction-id-prefix: prod-orders-instance-0-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: orders-transformer
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
    listener:
      ack-mode: record
~~~

This is an illustrative configuration **for a single instance**. When running multiple replicas, replace `instance-0` with a corresponding identifier. Do not copy the exact same fixed prefix across all pods.

Under suitable auto-configuration conditions, Spring Boot can create a `KafkaTransactionManager` from the prefix-configured producer factory. Listener containers can use that transaction manager if the corresponding wiring is in place. However, **having a prefix is not enough to guarantee every `@KafkaListener` is transactional**: verify the actual container factory, especially when multiple factories or custom configurations exist.

`isolation.level=read_committed` in the example is a **consumer** setting to read only records from committed transactions. It does not enable producer transactions and does not create a transaction with a database.

### Prefix sources for multiple replicas

A common convention is:

~~~text
<environment>-<application>-<instance-id>-tx-

production-orders-orders-0-tx-
production-orders-orders-1-tx-
staging-orders-orders-0-tx-
~~~

The `INSTANCE_ID` environment variable must be supplied per replica by the deployment platform and must not fall back to the same default across processes. With a Kubernetes StatefulSet, the ordinal is usually a stable identity source. With a Kubernetes Deployment, the pod name/UID can prevent collisions across live incarnations, though it changes across recreations; evaluate transaction lifecycles during rollouts and scaling.

If multiple environments share one Kafka cluster, the prefix should also include the environment/namespace. Using only `group.id` as the prefix is insufficient because all consumers in the group share the same group ID.

## 4. Configuring DefaultKafkaProducerFactory Directly

When not relying entirely on Spring Boot auto-configuration, an application can set the prefix via `setTransactionIdPrefix(...)`:

~~~java
@Bean
ProducerFactory<String, OrderEvent> orderProducerFactory() {
    Map<String, Object> config = new HashMap<>();
    config.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "kafka-1.example.internal:9092");
    config.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class);
    config.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class);

    DefaultKafkaProducerFactory<String, OrderEvent> factory =
            new DefaultKafkaProducerFactory<>(config);
    factory.setTransactionIdPrefix("prod-orders-instance-0-tx-");
    return factory;
}

@Bean
KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> orderProducerFactory) {
    return new KafkaTemplate<>(orderProducerFactory);
}
~~~

In the example, the broker address and prefix are placeholders for illustration. Production should obtain them from managed configuration, ensuring uniqueness across instances. The factory bean above creates transactional producers in the Spring Kafka-supported manner; **using a transaction** must still be driven by a transaction manager, `KafkaTemplate` local transaction, or appropriate container.

Do not configure the same raw `ProducerConfig.TRANSACTIONAL_ID_CONFIG` across all concurrent producers and expect Spring Kafka to resolve collisions automatically. That easily causes fencing. Let the producer factory manage suffixes and producer reuse.

### Local producer transactions

If you want to publish multiple Kafka records in the same transaction without a consumer listener:

~~~java
public void publishChanges(OrderCreated created, OrderConfirmed confirmed) {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders.events", created.orderId(), created);
        operations.send("orders.events", confirmed.orderId(), confirmed);
        return null;
    });
}
~~~

The example assumes the template uses a transactional producer factory and matching serializers. `executeInTransaction` creates a **local Kafka producer transaction** to group the two sends. It does not automatically include a listener's input offset in the transaction. Distinguish local transactions from listener container transactions.

## 5. Usage in Consume–Transform–Produce

When processing a source record and producing output records to Kafka, Spring Kafka can coordinate the producer transaction and source offset in the same Kafka transaction.

~~~mermaid
sequenceDiagram
    participant I as Input topic
    participant C as Transactional listener container
    participant L as Listener
    participant P as KafkaTemplate
    participant K as Kafka transaction coordinator
    participant O as Output topic
    I-->>C: poll record offset N
    C->>K: begin Kafka transaction
    C->>L: invoke listener
    L->>P: send result
    P->>O: Write record in transaction
    alt Listener succeeds
        C->>K: sendOffsetsToTransaction offset N+1
        C->>K: commit transaction
        Note over I,O: Output and source offset are committed
    else Listener throws exception
        C->>K: abort transaction
        C->>C: AfterRollbackProcessor handles
        Note over I,O: Failed transaction does not commit source offset
    end
~~~

Listener example:

~~~java
@KafkaListener(
        topics = "orders.commands",
        groupId = "orders-transformer",
        containerFactory = "transactionalListenerFactory")
public void transform(ConsumerRecord<String, OrderCommand> record) {
    OrderResult result = orderService.transform(record.value());
    resultKafkaTemplate.send(
            "orders.results",
            record.key(),
            result);
}
~~~

`transactionalListenerFactory` is an illustrative bean name for a listener container factory **already configured** with a matching Kafka transaction manager. `resultKafkaTemplate` must also use the right producer factory to participate in the container's Kafka transaction. Do not infer valid transactional behavior solely from a bean name or because a method has `@KafkaListener`.

When the listener returns normally and Kafka operations succeed, the container sends the processed record's offset into the transaction and commits. If the listener throws an exception, the container rolls back and invokes post-rollback handling (such as `DefaultAfterRollbackProcessor`) for redelivery or recovery as configured.

Do not catch and swallow exceptions when business processing fails. If a listener returns normally despite an incomplete mandatory step, the container may commit the transaction with partial results.

### read_committed downstream

Downstream consumers need `isolation.level=read_committed` if they should only receive committed data from transactional producers. Consumers using `read_uncommitted` may see records from uncommitted or aborted transactions under Kafka semantics.

`read_committed` does not mean every effect outside Kafka is exactly-once. It only controls the visibility of Kafka transactional records.

## 6. Scope of Prefix Uniqueness

`transactional.id` is scoped to the **Kafka cluster** transaction coordinator, not just within a single `group.id`. Therefore, the prefix namespace must avoid collisions across services, environments, and producer factories if they could generate the same full ID on the same cluster.

| Deployment | Suitable ID allocation | Risk to avoid |
|---|---|---|
| Single pod | Dedicated fixed prefix for the pod | Accidentally duplicating the config when scaling. |
| StatefulSet | Service + namespace + ordinal | Two processes with the same ordinal/prefix active during rollout overlap. |
| Deployment | Service + environment + unique pod identity | Shared fallback prefix or unmanaged ID churn. |
| Fixed VMs | Service + stable instance ID | Cloning VMs with identical configuration. |
| Multiple KafkaTemplates/factories | Distinct namespaces or shared factory with safe suffix management | Two independent factories generating the same transactional ID. |
| Multiple environments sharing a cluster | Include environment/tenant in namespace | Staging fencing production producers. |

A **stable** identity helps fence an old producer when a logical instance restarts. A **per-incarnation unique** identity can also avoid collisions, but producer lifecycle and stale transaction metadata must be managed. The choice depends on the deployment model; the invariant is that no two independent active transactional producers share the same full ID.

Do not generate a new UUID per record or per attempt to "avoid fencing". That creates excessive transactional identities, increases coordinator overhead, complicates cache management, and masks operational bugs.

## 7. Producer Cache, Concurrency, and Suffix Strategy

Spring Kafka can create or reuse multiple transactional producers from a single `DefaultKafkaProducerFactory`. An instance with multiple listener threads, local transactions, or concurrent publish tasks may need multiple producers simultaneously. Therefore, the factory manages suffixes and caching to prevent transactional ID collisions among concurrently used producers.

In supported versions, Spring Kafka provides `TransactionIdSuffixStrategy` / `DefaultTransactionIdSuffixStrategy` to control suffix allocation, including finite suffix pool mechanisms. When concurrent transactions exceed the pool's producer capacity, the application may encounter `NoProducerAvailableException`.

Points to remember:

- The prefix is the namespace of the instance/factory, **not** the number of producers.
- The suffix distinguishes transactional producers used concurrently within the same namespace.
- Producer caching reduces the cost of initializing producers and transactional identities.
- Too few producers or suffixes cause contention under higher concurrency.
- Too many producers/suffixes can increase unnecessary resources, connections, and transaction state.
- Suffix allocation and reuse details vary across Spring Kafka versions; never hard-code suffixes to partitions.

For example, a service with `concurrency=4` that also runs multiple `executeInTransaction` tasks may find a cache sized for a single producer insufficient. Measure concurrent transactions, transaction duration, and actual workload to size appropriately.

### Closing a producer does not necessarily close the connection

With Spring Kafka's transactional producer factory, the producer wrapper may be returned to the cache after a transaction finishes instead of immediately closing the underlying physical producer. The producer factory manages the lifecycle and can close all managed producers on application shutdown. Do not manually tamper with the underlying producer or invoke transaction APIs from another thread while Spring Kafka coordinates the transaction.

## 8. transactional.id Expiration and maxAge

Kafka brokers have a `transactional.id.expiration.ms` setting that expires metadata for inactive transactional IDs after a period. If a producer stays cached for a very long time and is reused after the broker has expired its identity, the application may fail on the next transaction.

In supporting Spring Kafka versions, `DefaultKafkaProducerFactory` provides `maxAge` to proactively refresh aged cached producers before the broker expires the transactional ID. When you have infrequently used producers or workloads with long idle periods, check your version and choose a `maxAge` sufficiently smaller than the broker threshold with a safety margin.

| Parameter | Location | Controls |
|---|---|---|
| `transactional.id.expiration.ms` | Broker | Metadata expiration for inactive transactional IDs. |
| `maxAge` | Spring Kafka producer factory (if supported) | Refreshes cached transactional producers based on age. |
| `transaction.timeout.ms` | Kafka producer | Maximum duration for a transaction before abort risk. |
| `max.poll.interval.ms` | Kafka consumer | Maximum interval allowed between two poll calls. |

Do not confuse fencing errors caused by **duplicate transactional IDs** with errors from expired cached producers. Increasing one timeout does not automatically resolve failures caused by the other parameter.

## 9. Transaction Timeout and Listener Processing Time

A Kafka transaction has a finite lifetime. If a listener makes very slow downstream calls while a transaction is open, it can exceed `transaction.timeout.ms`, and the Kafka coordinator may abort it. Meanwhile, if the consumer fails to return to `poll()` soon enough, it can exceed `max.poll.interval.ms`, triggering a group rebalance.

Example of a listener:

1. Poll source record.
2. Begin Kafka transaction.
3. Call HTTP API with a two-minute timeout.
4. Retry three times, waiting one minute each time.
5. Publish output and attempt to commit the Kafka transaction.

If the transaction timeout and poll interval are shorter than the total time, committing can fail. A valid prefix cannot make an expired transaction valid.

Recommendations:

- Bound HTTP/database timeouts and each retry attempt.
- Keep Kafka transactions short, clear, and with enough margin for commit.
- Avoid long `Thread.sleep` calls inside transactional listeners.
- Use a retry/rollback policy aligned with poll and transaction deadlines.
- For work that needs to wait minutes or hours, consider moving it into a durable workflow or transactional outbox.

Kafka brokers can cap the maximum `transaction.timeout.ms` via broker configuration, so timeouts cannot be raised arbitrarily.

### Retries and non-blocking retries

With a transactional listener container, errors typically roll back the Kafka transaction and pass through `AfterRollbackProcessor`/`DefaultAfterRollbackProcessor`. Do not blindly apply non-transactional `DefaultErrorHandler` assumptions.

Standard non-blocking retries via `@RetryableTopic` **do not combine directly with Kafka container transactions** in Spring Kafka. If long delays in retry topics are needed, redesign transaction boundaries or use a different pattern; do not simply add the annotation expecting "exactly-once retry".

## 10. Failure Windows and Scope of Guarantees

Kafka transactions coordinate **Kafka operations within the same transaction**. They do not automatically cover database transactions or HTTP services.

| Scenario | What Kafka transactions support | Additional measures needed |
|---|---|---|
| Publish multiple Kafka output records | Commit/abort records in the same Kafka transaction | Ensure all sends join the transaction; downstream read committed. |
| Consume–transform–produce Kafka | Commit outputs and source offsets atomically in the same Kafka transaction | Proper container/template/manager wiring, abort handling. |
| Consumer updates a database | Does not cover database updates | Inbox, unique event ID, and database transaction. |
| Database update then send Kafka event | Does not atomically commit DB+Kafka | Transactional outbox or separate coordination protocol. |
| HTTP call inside listener | Kafka abort does not undo a succeeded HTTP request | Idempotency key and handling uncertain outcomes. |
| DLT publish during recovery | Depends on specific transaction/recoverer policy | Verify DLT send and offset commit; preserve replayability. |

For example, if the database commits but the process dies before the Kafka transaction commits, the source record may be read again. Without idempotency, the database may be updated twice. Thus, even when using Kafka transactional listeners, consumers with side effects outside Kafka still need duplicate protection.

## 11. Common Incidents

### Duplicate prefix across pods

**Symptoms:** repeated `ProducerFencedException`, transaction aborts during rollouts, rising consumer lag.

**Cause:** multiple producer factories share a prefix and generate identical transactional IDs.

**Resolution:** inspect the effective prefix of each replica/factory, fix the `INSTANCE_ID` source, check rollout overlaps, and never reuse a fenced producer.

### Prefix changing per message

**Symptoms:** huge number of transactional identities, hard-to-manage coordinator metadata, poor producer reuse.

**Cause:** code creates a new producer factory or UUID transaction ID for every event.

**Resolution:** configure prefixes per instance, keep producer factories lifecycle-managed, and let Spring Kafka manage suffixes/caching.

### Insufficient producer cache

**Symptoms:** on versions with a finite suffix pool, `NoProducerAvailableException` occurs under high load.

**Cause:** concurrency exceeds the number of producers/suffixes that can be allocated.

**Resolution:** inspect producer pools, local transactions, listener concurrency, and sizing; increase cache capacity appropriately or limit concurrent transactions.

### Fencing after long idle periods

**Symptoms:** the first transaction after an idle period fails even though steady-state transactions are stable.

**Possible causes:** aged cached producer or expired broker transactional ID; could also be another identity collision.

**Resolution:** compare broker expiration, Spring Kafka `maxAge`, error classes in logs, and factory lifecycle; do not jump to a single cause from one exception alone.

### Prefix set, yet offsets are not atomic with output

**Symptoms:** output is written, but a restart causes source records to be reprocessed, or offsets advance outside the expected transaction.

**Cause:** listener container is not using the right Kafka transaction manager, or the template sends outside the container's transaction.

**Resolution:** inspect the container factory, template, producer factory, and transaction manager; test a crash before commit and observe both committed offsets and output with a `read_committed` consumer.

## 12. Observability for transactionIdPrefix

For production diagnostics, correlate transaction logs with instance identity and consumer assignments.

| Signal | Observation goal |
|---|---|
| Instance ID + effective prefix | Prove each replica has a non-overlapping namespace. |
| Transaction begin/commit/abort | Detect unfinished transactions or unusual abort spikes. |
| `ProducerFencedException` / epoch errors | Detect identity collisions or stale producers. |
| `NoProducerAvailableException` | Detect insufficient suffix/cache capacity in applicable versions. |
| Transaction duration p95/p99 | Detect listeners holding transactions too long. |
| Producer pool/cache size | Track active transactional producers in use. |
| Consumer lag and rebalances | Correlate transaction errors with offset progress. |
| Downstream read-committed output | Confirm successful Kafka outputs are readable. |
| External DB idempotency outcomes | Detect duplicates crossing outside Kafka boundaries. |

Logs should include service, environment, instance ID, group ID, listener ID, topic/partition/offset, transaction status, and exception class. Log transactional IDs/prefixes only when needed for diagnosis and with controlled cardinality; do not put event IDs in metric labels where they cause series explosion. Never log tokens, passwords, or sensitive payloads.

## 13. Runbook for ProducerFencedException

1. Identify the cluster, namespace, service, instance, producer factory, and full transactional ID if available.
2. Find all pods/processes that could generate that same ID, including old processes not yet terminated during a rollout.
3. Check the `INSTANCE_ID` source, default fallbacks, per-environment prefixes, and suffix allocation.
4. Distinguish legitimate fencing of an old producer from two active instances colliding on identity unintentionally.
5. Fix the prefix source and stop misconfigured instances according to deployment procedures.
6. Initialize a fresh producer with the proper identity; do not attempt to reuse a fenced producer.
7. Reconcile source offsets and committed outputs; verify idempotency when records are redelivered.
8. Monitor aborts/fencing and lag during subsequent rollouts.

Do not "fix" this by disabling transactions application-wide or generating a new random prefix per message. That may hide symptoms while breaking design guarantees.

## 14. Runbook for Transaction Abort or Timeout

1. Read the root exception from the listener, template, transaction manager, and Kafka broker.
2. Measure transaction duration and time between polls; compare `transaction.timeout.ms` against `max.poll.interval.ms`.
3. Inspect blocking I/O calls, retries, backoff, and batch sizes.
4. Check coordinator/broker health, ACLs, connectivity, and conflicting transaction IDs.
5. Verify rollback/recovery/`DefaultAfterRollbackProcessor` behavior for your version.
6. Shorten transactions or re-architect overly long work.
7. Verify committed offsets, `read_committed` outputs, and business state after recovery.

## 15. Runbook When Scaling to Multiple Replicas

1. List all deployments and producer factories using transactional producers on the same cluster.
2. Design a prefix convention containing environment, service, and unique instance identity.
3. Verify each replica does not fall back to a shared default.
4. Measure concurrency and size producer suffix/cache capacity for concurrent transactions.
5. Test rolling restarts, crashes, lingering old processes, and reconnects after network partitions.
6. Verify fencing, commit/abort behavior, input offsets, and `read_committed` outputs.
7. Monitor the broker transaction coordinator, producer pools, group lag, and transactional ID errors after scaling.

If a single JVM has multiple independent producer factories sharing the same prefix, transactional ID collisions can still happen. Uniqueness applies to actual producer IDs in the Kafka cluster, **not merely** to the number of pods.

## 16. Pre-Deployment Checklist

| Checkpoint | Question to answer | Evidence |
|---|---|---|
| Prefix configuration | Is `transactionIdPrefix` configured on the right producer factory? | Effective Boot properties or bean config. |
| Identity uniqueness | Do replicas/factories avoid transactional ID collisions? | Instance → prefix mapping, suffix strategy. |
| Container transaction | Does the listener use the right Kafka transaction manager? | Container factory and begin/commit/abort logs. |
| Template participation | Does the output KafkaTemplate join the listener transaction? | Producer factory wiring and fault injection. |
| Consumer visibility | Do downstream consumers needing transactional semantics use `read_committed`? | Consumer effective config. |
| Producer cache | Are pool/suffix limits sufficient for concurrent transactions? | Concurrency, cache metrics, availability exceptions. |
| Expiration | Are long-idle producers managed? | Broker expiration, `maxAge`, and lifecycle logs. |
| Timeout | Do transaction and poll deadlines fit the workload? | Duration p99, timeout configs, and retry policy. |
| Failure handling | Do listener errors roll back/retry/recover properly? | AfterRollbackProcessor and DLT outcomes. |
| External consistency | Do DB/HTTP layers prevent duplicates outside Kafka transactions? | Inbox/outbox, idempotency tests. |

**Conclusion:** `transactionIdPrefix` is how Spring Kafka namespaces `transactional.id` values for transactional producers. Proper setup ensures unique IDs across concurrently active instances/factories, applies an appropriate producer cache/suffix strategy, and manages timeouts/expiration to avoid fencing. Only then should you wire the transaction manager, listener container, and `KafkaTemplate` to achieve atomicity between Kafka outputs and input offsets. A correct prefix is foundational to Kafka reliability, but it does not automatically provide exactly-once guarantees for databases, HTTP calls, or effects outside Kafka.
