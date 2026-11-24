# KafkaTransactionManager

## 1. What is KafkaTransactionManager?

`KafkaTransactionManager<K, V>` is Spring Kafka's transaction manager used to manage **Kafka producer transactions** through the Spring transaction infrastructure. When an application opens a transaction with this manager, sends via `KafkaTemplate` using the matching transactional `ProducerFactory` can participate in a shared Kafka transaction.

A Kafka transaction allows grouping multiple records sent to Kafka topics/partitions and committing or aborting them as a single unit. In a consume–process–produce flow, a transactional listener container can also send the consumed record's offset into the same Kafka transaction as the output records.

~~~text
Business service
       |
       v
KafkaTransactionManager opens transaction
       |
       +--- KafkaTemplate.send(topic A, event A)
       |
       +--- KafkaTemplate.send(topic B, event B)
       |
       v
Commit or abort Kafka transaction
~~~

Key distinctions:

- **A successful send** does not mean the transaction has committed.
- **A successful transaction commit** confirms that the transactional records were committed by Kafka, but does not prove that a downstream consumer has processed them.
- **A Kafka transaction** does not automatically include a database transaction, HTTP request, or email.
- A consumer using `read_committed` will not see records belonging to an aborted transaction; a `read_uncommitted` consumer may read those records.

KafkaTransactionManager integrates Spring with the Kafka transaction protocol. It does not replace the Kafka broker's transaction coordinator and does not create an XA distributed transaction between Kafka and external systems.

## 2. Participating Components

| Component | Responsibility |
|---|---|
| `KafkaTransactionManager<K, V>` | Starts, commits, and rolls back transactions through Spring |
| `ProducerFactory<K, V>` | Provides Kafka producers to KafkaTemplate |
| `DefaultKafkaProducerFactory` | Creates and manages transactional producers, caching, and lifecycle |
| `KafkaTemplate<K, V>` | Sends records using the producer bound to the active transaction |
| `KafkaProducer` | Executes begin/send/commit/abort in the Kafka client |
| Broker transaction coordinator | Manages transaction state by transactional ID |
| Spring listener container | Manages consume–process–produce and sends offsets into the Kafka transaction |
| `read_committed` consumer | Reads only committed transactional records |

These components have distinct responsibility boundaries. `KafkaTemplate` is the message-sending API; `KafkaTransactionManager` defines the transaction boundary; the producer and broker actually execute the transaction protocol.

## 3. First Prerequisite: Transactional ProducerFactory

### 3.1. Transaction ID prefix

A regular Kafka producer does not automatically participate in Kafka transactions. `DefaultKafkaProducerFactory` must be configured with a **transaction ID prefix** to create transactional producers with distinct `transactional.id` values.

In Spring Boot, a common configuration is:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-tx-instance-a-
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        transaction.timeout.ms: 60000
~~~

`orders-tx-instance-a-` is only an illustrative value. In a multi-instance deployment, the prefix must differ across concurrently running instances. If two producers use the same transactional ID, one producer can be fenced by the broker.

Spring Boot typically auto-configures `KafkaTransactionManager` when a transactional producer factory is configured via `spring.kafka.producer.transaction-id-prefix` and there are no conflicting custom beans. Verify the actual beans when an application has multiple producer factories or templates.

### 3.2. transaction.id is not an event ID

`transactional.id` identifies a logical transactional producer. Kafka uses the ID together with the producer epoch to prevent an older producer from continuing to send after ownership of the ID has transferred to another producer.

It is not a business event ID. If a service emits the same `OrderCreated` in two different transactions, Kafka does not automatically treat it as a duplicate business event. A stable event ID and consumer idempotency are still required when there are business retries or side effects outside Kafka.

### 3.3. Producer cache

`DefaultKafkaProducerFactory` can reuse transactional producers from a cache. The number of producers required depends on the application's transaction concurrency. If many listener threads or many producer-only transactions run in parallel, monitor producer resources and how the factory provisions corresponding producers.

Do not manually create a new `KafkaProducer` per record and do not manually close a factory-managed producer inside a service. Letting Spring/Kafka manage the lifecycle keeps transaction and resource binding consistent.

## 4. Begin, Send, Commit, and Abort Flow

~~~mermaid
sequenceDiagram
    participant S as Business service
    participant M as KafkaTransactionManager
    participant T as KafkaTemplate
    participant P as Transactional producer
    participant B as Kafka broker

    S->>M: Begin transaction
    M->>P: beginTransaction()
    S->>T: send(topicA, recordA)
    T->>P: send recordA
    P->>B: Produce request
    S->>T: send(topicB, recordB)
    T->>P: send recordB
    P->>B: Produce request
    alt Success
        S->>M: Commit
        M->>P: commitTransaction()
        P->>B: Commit transaction
    else Rollback
        S->>M: Rollback
        M->>P: abortTransaction()
        P->>B: Abort transaction
    end
~~~

General sequence:

1. Spring transaction infrastructure selects `KafkaTransactionManager`.
2. The manager obtains a transactional producer from `ProducerFactory` and opens a Kafka transaction.
3. The producer is bound to the current transaction context via Spring's resource synchronization mechanism.
4. `KafkaTemplate` obtains the appropriate producer to send records within the transaction.
5. The transaction manager commits if the transaction finishes successfully.
6. If an error requires a rollback, the manager aborts the transaction.
7. The producer is cleaned up/returned to the cache according to the factory's policy.

Calling `send()` returns a future. The future may complete successfully before the Kafka transaction commits. If the transaction later aborts, the Produce request result still does not prove that the record is visible to `read_committed` consumers.

## 5. Declaring KafkaTransactionManager in Java

If the application already has a transactional `ProducerFactory`, you can declare the bean:

~~~java
@Configuration
@EnableTransactionManagement
public class KafkaTxConfiguration {

    @Bean
    public KafkaTransactionManager<String, OrderEvent>
            kafkaTransactionManager(
                ProducerFactory<String, OrderEvent> producerFactory
            ) {

        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean
    public KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory
    ) {
        return new KafkaTemplate<>(producerFactory);
    }
}
~~~

The `producerFactory` bean in the example must have a transaction ID prefix. Otherwise, merely creating the manager does not make the producers transactional.

When multiple factories exist, use qualifiers for the manager and template to avoid the manager pointing to factory A while `KafkaTemplate` uses factory B. Connecting to the same bootstrap servers does not mean two factories share a transaction.

### 5.1. Selecting the manager explicitly

An application may simultaneously have `JpaTransactionManager`, `DataSourceTransactionManager`, and `KafkaTransactionManager`. In that case, `@Transactional` without specifying a manager may pick an unintended default manager.

Specify it explicitly:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publishEvents() {
    // ...
}
~~~

The exact bean name depends on how the application registers transaction managers. Ensure the code is invoked through a Spring-managed proxy so the annotation takes effect.

## 6. Producer-Only Transactions with @Transactional

A service sending multiple Kafka events in a single transaction:

~~~java
@Service
@RequiredArgsConstructor
public class OrderPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publishOrder(OrderCreatedEvent created) {
        kafkaTemplate.send(
            "order-events",
            created.orderId(),
            created
        );

        kafkaTemplate.send(
            "order-audit",
            created.orderId(),
            new OrderAuditEvent(created.orderId(), "CREATED")
        );
    }
}
~~~

When the method is called through a Spring proxy, the manager starts a transaction before entering the method and commits after the method completes. Both records are sent within the same transaction according to the `KafkaTemplate`/`ProducerFactory` configuration.

If the method throws an exception matching the rollback rules, Spring triggers an abort. With `@Transactional`, default rollback usually applies to unchecked exceptions and `Error`; checked exceptions require configuring rollback if desired:

~~~java
@Transactional(
    transactionManager = "kafkaTransactionManager",
    rollbackFor = Exception.class
)
public void publishOrThrow() throws Exception {
    kafkaTemplate.send("order-events", "order-42", event);

    if (businessRuleFailed()) {
        throw new Exception("Abort Kafka transaction");
    }
}
~~~

If a listener/service catches the exception and returns normally, Spring may treat the transaction as successful and commit it. Either let the exception cross the transaction boundary or explicitly mark the transaction rollback-only.

### 6.1. Commit failure after the method body finishes

The transaction interceptor commits only after the method body finishes. Therefore, code inside the method should not log "Kafka transaction committed" right after the last `send()`.

Commit can still fail due to the broker, transaction timeout, producer fencing, or I/O errors. Callers must observe the final outcome of the call passing through the transaction interceptor, not only the send future of each individual record.

### 6.2. Thread-bound transaction context

Spring's resource binding is normally tied to a thread. If code inside a transactional method offloads sending to `CompletableFuture.runAsync(...)` or another executor thread, the transaction context does not automatically propagate.

Incorrect assumption:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publishAsync(OrderEvent event) {
    CompletableFuture.runAsync(
        () -> kafkaTemplate.send("order-events", event.orderId(), event)
    );
}
~~~

The method may finish and commit before the background task executes the send; the task running on another thread may not participate in the transaction. Execute `KafkaTemplate.send` calls inside the transaction scope, as the Kafka producer itself already supports asynchronous sending at the I/O layer.

### 6.3. Self-invocation

With proxy-based Spring transactions, method A calling method B on the same object can bypass B's transaction interceptor.

~~~java
public void handleOrder(OrderEvent event) {
    publishTransactional(event);  // internal call, not through proxy
}

@Transactional(transactionManager = "kafkaTransactionManager")
public void publishTransactional(OrderEvent event) {
    kafkaTemplate.send("order-events", event.orderId(), event);
}
~~~

You can extract the transactional operation into another bean or use `TransactionTemplate` to avoid relying on self-invocation.

## 7. TransactionTemplate and KafkaTemplate.executeInTransaction

### 7.1. Spring TransactionTemplate

`TransactionTemplate` provides a programmatic transaction boundary:

~~~java
@Service
public class KafkaOrderService {

    private final KafkaTemplate<String, OrderEvent> template;
    private final TransactionTemplate transactionTemplate;

    public KafkaOrderService(
        KafkaTemplate<String, OrderEvent> template,
        KafkaTransactionManager<String, OrderEvent> manager
    ) {
        this.template = template;
        this.transactionTemplate = new TransactionTemplate(manager);
    }

    public void sendBoth(OrderEvent first, OrderEvent second) {
        transactionTemplate.executeWithoutResult(status -> {
            template.send("order-events", first.orderId(), first);
            template.send("order-events", second.orderId(), second);
        });
    }
}
~~~

`TransactionTemplate` handles begin, commit, and rollback around the callback. It is useful when an explicit boundary is needed or when placing a transaction on a service method is inconvenient.

### 7.2. KafkaTemplate.executeInTransaction

`KafkaTemplate` also provides a local transaction API:

~~~java
public void sendBoth(OrderEvent first, OrderEvent second) {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("order-events", first.orderId(), first);
        operations.send("order-events", second.orderId(), second);
        return null;
    });
}
~~~

This opens a local Kafka transaction around the callback using the transactional template. Note that `executeInTransaction` has its own scope semantics and should not be assumed to join an outer transaction managed by `KafkaTransactionManager`. Choose the appropriate boundary and avoid nesting transaction mechanisms unnecessarily.

| Usage pattern | Boundary | Suitable scenario |
|---|---|---|
| `@Transactional("kafkaTransactionManager")` | Spring transaction interceptor | Service method sending multiple Kafka records |
| `TransactionTemplate` | Spring transaction callback | Programmatic transaction control |
| `KafkaTemplate.executeInTransaction` | Local Kafka transaction | Standalone producer-only callback |
| Transactional listener container | Container transaction | Consume–process–produce |

## 8. Consume–Process–Produce with KafkaTransactionManager

An important use case is reading a record from Kafka, computing a result, emitting output records to Kafka, and sending the source offset into **the same Kafka transaction**.

~~~text
Input topic "payments"
      |
      v
Transactional listener container
      |
      +-- Receive input record
      +-- Run business logic
      +-- KafkaTemplate.send("payment-results", result)
      +-- Send input consumer offset to transaction
      |
      v
Commit Kafka transaction
      |
      +-- Output is committed
      +-- Input offset is also committed
~~~

If the transaction aborts, output records are not visible to `read_committed` consumers and the input offset is not committed in that transaction. The source record can be redelivered after rollback/seek according to the container settings.

### 8.1. Why must the offset be in the same transaction?

If the output is committed first and the source offset is committed separately afterward, a crash between the two steps leaves the Kafka output written while the source offset has not advanced. The source record may be read again and the output emitted twice.

When output and offset participate together in the Kafka transaction, both outcomes are committed or aborted according to the transaction protocol. This is the foundation for exactly-once semantics in Kafka-to-Kafka flows.

### 8.2. Transactional listener

Example of a listener sending results to another Kafka topic:

~~~java
@Component
@RequiredArgsConstructor
public class PaymentListener {

    private final KafkaTemplate<String, PaymentResult> template;

    @KafkaListener(
        topics = "payment-requests",
        groupId = "payment-processor",
        containerFactory = "transactionalListenerContainerFactory"
    )
    public void onPayment(PaymentRequested request) {
        PaymentResult result = calculateResult(request);

        template.send(
            "payment-results",
            request.paymentId(),
            result
        );
    }
}
~~~

The listener container must be configured as transactional and use a matching producer factory. Do not manually call `commitSync()` inside the listener to commit source offsets when the container is managing the transaction.

### 8.3. Configuring the container factory

With Spring Kafka versions that support a Kafka-aware transaction manager on container properties:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, PaymentRequested>
        transactionalListenerContainerFactory(
            ConsumerFactory<String, PaymentRequested> consumerFactory,
            KafkaTransactionManager<String, PaymentResult> kafkaTxManager
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, PaymentRequested>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setKafkaAwareTransactionManager(kafkaTxManager);

    return factory;
}
~~~

The exact API method to attach the transaction manager depends on the Spring Kafka version. Older versions may provide `setTransactionManager(...)`, whereas newer versions use the Kafka-aware API. Check the Javadoc of the actual dependency when writing Java configuration and ensure the right factory bean is used by `@KafkaListener`.

If using Spring Boot auto-configuration or a custom container factory, verify that the Kafka transaction manager is actually attached to the container; merely enabling `transaction-id-prefix` on the producer is not enough for every listener to become transactional automatically.

## 9. Exactly-Once Semantics and read_committed

Kafka transactions provide atomicity for Kafka operations within the transaction. Consumers wanting to avoid reading records from aborted transactions must configure:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
      enable-auto-commit: false
~~~

`read_committed` returns only committed transactional records and filters out aborted records. It may also wait while an open transaction sits ahead of the safely readable position (last stable offset). Therefore, long-running open transactions can affect consumer lag and record visibility latency.

| Consumer isolation | Behavior with transactional records |
|---|---|
| `read_committed` | Does not read aborted transactions; returns only committed records |
| `read_uncommitted` | May read records belonging to aborted or in-flight transactions |

Kafka EOS does not guarantee that a listener is invoked only once under all conditions. Input records can be redelivered when a transaction aborts. What is guaranteed in a Kafka-to-Kafka flow is that transaction outputs and offsets are coordinated atomically when proper transactional processing and consumer isolation are used.

### 9.1. Not exactly-once for databases

If a listener writes to a database and then sends Kafka output, the database transaction is a separate resource:

~~~java
@KafkaListener(topics = "orders")
public void onOrder(OrderCreated event) {
    orderRepository.save(...);          // SQL side effect
    kafkaTemplate.send("results", ...); // Kafka transaction
}
~~~

The database can commit successfully while the Kafka transaction aborts. The input is redelivered and the database side effect may run again. A unique constraint, inbox table, or idempotent upsert is required to handle this.

## 10. KafkaTransactionManager and Database Transaction Managers

Spring may have multiple transaction managers:

- `JpaTransactionManager` for the JPA persistence context and database.
- `DataSourceTransactionManager` for JDBC.
- `KafkaTransactionManager` for the Kafka producer.

`@Transactional` without specifying a manager is not enough to determine how resources are coordinated. If code updates a database and publishes a Kafka event, you must determine which manager is primary and whether the Kafka transaction is synchronized with the other transaction.

### 10.1. Transaction synchronization

Spring Kafka allows synchronizing a Kafka producer transaction with an existing Spring transaction, such as a database transaction. With the database as primary, the commit flow may look like:

~~~text
Begin database transaction
    |
    +-- Update domain tables
    +-- KafkaTemplate sends in synchronized Kafka transaction
    |
    v
Commit database
    |
    v
Commit Kafka
~~~

If the database commits successfully but the Kafka commit fails, the two systems become out of sync. Transaction synchronization is not two-phase commit/XA. Resource commit order and how exceptions propagate depend on configuration/version, so cross-resource atomicity must not be assumed.

### 10.2. Nested transactions

Nested transaction boundaries can be arranged to change the commit order between Kafka and the database. However, changing the order only shifts the failure window: Kafka could commit before the DB and then the DB fails, or the DB commits before Kafka and then Kafka fails.

Do not use nested transactions as an "automatic synchronization" mechanism without analyzing ordering, rollback rules, proxies, and exception propagation.

### 10.3. Transactional outbox

When database state and Kafka events must remain consistent, a transactional outbox is usually more reliable than transaction synchronization:

1. Within the same database transaction, write the business data and an outbox row.
2. Commit the database.
3. A publisher reads unpublished outbox rows.
4. The publisher sends the Kafka record and awaits the result.
5. Mark the outbox row as processed or persist progress.

~~~mermaid
flowchart LR
    S[Business service] --> T[Database transaction]
    T --> D[Domain tables]
    T --> O[Outbox table]
    O --> P[Outbox publisher]
    P --> K[Kafka topic]
~~~

If the Kafka send succeeds but the publisher crashes before marking the outbox row, it may re-emit the same event. Therefore, outbox typically provides at-least-once semantics and still requires an event ID along with an idempotent consumer.

`KafkaTransactionManager` can help the publisher emit multiple Kafka output records in one transaction, but it does not turn updating the outbox table into a Kafka XA transaction.

## 11. Fencing and Producer Identity

### 11.1. Producer fencing

Kafka uses `transactional.id` and the producer epoch to prevent an old producer from writing once a new producer has taken over the same identity. When a producer is fenced, it may encounter `ProducerFencedException` or an equivalent error.

This is a critical error that requires proper lifecycle handling. A fenced producer must not continue to be used for subsequent transactions; it must be stopped/recreated according to the Kafka client/factory mechanism, and the cause of the duplicate ID must be investigated.

### 11.2. Unique prefixes across instances

For example, three pods should not share the same prefix if doing so leads to duplicate transactional IDs:

~~~text
Invalid if running concurrently with the same suffix:
  orders-tx-
  orders-tx-
  orders-tx-

Better when each instance has its own prefix:
  orders-tx-pod-a-
  orders-tx-pod-b-
  orders-tx-pod-c-
~~~

During Kubernetes rollouts, also consider the overlap phase when old and new pods run simultaneously. The prefix must be tied to a sufficiently unique identity so collisions do not occur during overlap.

### 11.3. Static membership differs from transactional identity

The consumer property `group.instance.id` serves consumer group static membership. It does not replace the producer's `transactional.id`.

The two identities solve different problems:

- `group.instance.id` helps the coordinator recognize a static consumer member.
- `transactional.id` helps Kafka manage and fence transactional producers.

Do not swap them or use one property in place of the other.

## 12. Transaction Timeout

Kafka producer transactions have a timeout. If a transaction is kept open too long, the broker can abort it and the subsequent commit will fail.

Common causes:

- Listener processing an overly large batch.
- Synchronous HTTP calls without timeouts.
- Long-running database queries or lock waits.
- Blocking retries inside a transactional listener.
- Slow broker/network.
- Code keeping a transaction open across unrelated work.

Configurations to review:

| Configuration / metric | Meaning |
|---|---|
| `transaction.timeout.ms` | Duration a Kafka transaction is allowed to stay open |
| Broker transaction timeout limit | Maximum timeout accepted by the broker |
| `request.timeout.ms` | Time the producer waits for a request response |
| `delivery.timeout.ms` | Upper bound for produce delivery |
| `max.poll.interval.ms` | Limit between consumer poll calls |
| Transaction duration | Actual duration of the transaction |
| Commit/abort latency | Latency to finalize the transaction |

Do not increase timeouts indefinitely to mask a listener that can hang. Set dedicated timeouts for database/HTTP calls, reduce batch size, or move slow work outside the transaction where possible.

## 13. Common Errors in Kafka Transactions

| Error | Common meaning | Investigation |
|---|---|---|
| `ProducerFencedException` | Producer lost ownership of the transactional ID | Duplicate prefix, pod overlap, lifecycle |
| `InvalidProducerEpochException` | Producer epoch is no longer valid | Fencing and transaction state |
| `InvalidTxnStateException` | Invalid operation for the current transaction state | Begin/commit/abort sequence and prior errors |
| `TimeoutException` | Request, delivery, or commit did not finish in time | Broker, network, timeouts |
| `AuthorizationException` | Missing permissions on topic/transactional ID | Principal and ACLs |
| `SerializationException` | Failed to serialize record | Serializer and schema |
| Kafka commit failure | Cannot confirm whether the transaction committed | Treat state as uncertain; investigate before retrying |
| Application exception | Transaction rolled back per Spring policy | Transaction boundary and rollback rules |

In particular, a timeout at commit time can leave the caller uncertain of the final outcome. Do not assume "timed out" means Kafka did not write the records. Log the event ID/correlation ID and make downstream processing idempotent so retries do not create duplicate side effects.

## 14. Retry and After-Rollback Processing

With a transactional listener container, a listener error must lead to transaction rollback/abort if business processing did not succeed. After rollback, Spring Kafka can use an `AfterRollbackProcessor` to control seek, redelivery, or recovery.

`DefaultAfterRollbackProcessor` is a common component in this flow. Do not attach a `DefaultErrorHandler` that swallows exceptions without understanding transactional container semantics.

Listener example:

~~~java
@KafkaListener(
    topics = "payments",
    containerFactory = "transactionalListenerContainerFactory"
)
public void onPayment(PaymentRequested event) {
    paymentService.processAndPublish(event);
    // If failed, throw an exception so the container rolls back the transaction.
}
~~~

When designing recovery for a transactional listener, clarify:

- Which records will be redelivered after rollback?
- Where do blocking retries happen and for how long?
- When retries are exhausted, what does the recoverer/DLT do?
- Could a failed DLT publish cause the source offset to be committed incorrectly?
- Does committing the recovered offset use a separate transaction?
- Are there database side effects that require idempotency?

Do not assume non-blocking retry topics combine automatically with transactional listeners; Spring Kafka has limitations when combining non-blocking retries with container transactions.

## 15. Kafka Transactions Do Not Replace Idempotency

Cases that can still produce business duplicates even when the producer uses transactions:

- A client retries an event-emitting API after an ambiguous timeout.
- The application sends the same event in two independent transactions.
- The listener updates the database, but the Kafka transaction aborts.
- A `read_uncommitted` consumer reads records from an aborted transaction.
- A DLT publish succeeds, but the source recovery state has not committed.
- A new consumer group replays history.

For each business event, use a stable event ID; on the receiving side, apply a unique constraint, inbox table, or idempotent upsert. Kafka transactions protect atomicity within the Kafka log, while idempotency protects side effects when an event is delivered multiple times.

## 16. Observability for KafkaTransactionManager

A transaction can fail at begin, send, commit, or abort. Logging only `KafkaTemplate.send` is not enough to know the final outcome.

| Signal | Purpose |
|---|---|
| Transaction begin count | Count opened transactions |
| Commit success/error | Final commit outcome |
| Abort count | Distinguish rollbacks from business vs infrastructure causes |
| Commit latency | Detect slow coordinator/broker |
| Transaction duration | Detect transactions held open too long |
| Producer fencing errors | Detect duplicate transactional IDs |
| Producer send error/retry rate | Track Produce requests within transactions |
| Consumer lag | Monitor consumer progress |
| read_committed visibility delay | Impact of open transactions on downstream |
| Listener processing duration | Business execution duration |
| Offset/group errors | Investigate redeliveries |

Exact metric names depend on the Kafka client, Spring Kafka, and your observability stack. Combine producer metrics, listener/container metrics, transaction logs, and business event IDs.

Do not use event IDs as metric labels due to high cardinality; put event IDs in structured logs or traces. Avoid logging payloads containing sensitive data.

## 17. Transaction Testing Scenarios

### 17.1. Successful producer-only commit

1. Create a transactional producer factory and `KafkaTransactionManager`.
2. Start a transaction and send two records to two topics.
3. Let the transaction commit.
4. Read using a `read_committed` consumer.
5. Verify both records are readable after commit.

### 17.2. Producer-only abort

1. Send two records inside a transaction.
2. Throw an exception matching the rollback rules.
3. Verify the transaction is aborted.
4. Read again with a `read_committed` consumer.
5. Verify the aborted records are not received.

### 17.3. Consume–process–produce crash before commit

1. Send a source record with an event ID.
2. The transactional listener reads it and sends output.
3. Stop the process before the transaction commits in a controlled test scenario.
4. Restart with the same group ID.
5. Verify the source record can be redelivered since the source offset was not committed.
6. Verify the aborted output does not appear to a `read_committed` consumer.
7. Let the subsequent attempt commit and observe both output and offset.

### 17.4. Producer fencing

1. In a test environment, create two transactional producers attempting to use the same transactional ID.
2. Observe the older producer being fenced according to the protocol.
3. Verify the application does not continue using the fenced producer.
4. Change the prefix so there is no collision and retest.

### 17.5. Database side effect

1. Have a listener update the database and then publish to Kafka.
2. Inject a Kafka commit failure after the database commits.
3. Verify the two resources can temporarily be inconsistent.
4. Verify idempotency or outbox can restore the desired state.
5. Test duplicate handling when the event is replayed.

Tests must verify the actual state of Kafka outputs, consumer offsets, and the database. A method return or completed send future does not prove that a Kafka transaction committed.

## 18. Common Design Mistakes

**Creating KafkaTransactionManager with a non-transactional factory:** the manager cannot properly open Kafka transactions when producers lack a transaction ID prefix.

**Having multiple transaction managers without specifying one in `@Transactional`:** code may use the database manager instead of Kafka.

**Duplicate transactional IDs across pods:** the broker may fence a producer; infinite retries on that producer will not resolve ownership.

**Treating successful `KafkaTemplate.send` as transaction commit:** a transaction can still abort after send completes.

**`read_uncommitted` consumer:** can read aborted records even though the producer uses transactions.

**Treating Kafka + database as one XA transaction:** `KafkaTransactionManager` does not automatically guarantee atomic commits across two resources.

**Holding a transaction open across slow HTTP calls:** easily leads to timeouts and delays downstream visibility.

**Self-invocation:** the `@Transactional` annotation may not execute through the proxy.

**Sending on another thread:** the transaction context does not automatically propagate to executor threads.

**Swallowing exceptions in a transactional listener:** may cause the container to commit even though business processing did not complete.

**Using the wrong `KafkaTemplate`/`ProducerFactory`:** sends may not participate in the active transaction.

**Not tracking commit/abort outcomes:** makes it impossible to know whether records were committed or merely sent.

**No idempotency:** business retries and external side effects remain at risk of duplication.

## 19. Choosing KafkaTransactionManager for Production

| Requirement | Suitable design | Key considerations |
|---|---|---|
| Send multiple Kafka records atomically | KafkaTransactionManager + Spring transaction boundary | Transactional factory, commit/abort |
| Short producer-only callback | `KafkaTemplate.executeInTransaction` | Local transaction scope |
| Consume Kafka then write Kafka with offsets | Transactional listener container | Offset-in-transaction, read_committed |
| Consistent SQL write and Kafka publish | Transactional outbox | No XA; requires idempotency |
| Avoid reading aborted records | `read_committed` consumer | Last stable offset and latency |
| Multi-instance execution | Unique transaction ID prefix | Producer fencing and lifecycle |
| Retry after transactional listener failure | Rollback + AfterRollbackProcessor | DLT/recovery and offset correctness |

A practical rollout checklist:

1. Clearly identify which resources need atomicity: Kafka-only or Kafka with external systems.
2. Use a transactional producer factory with distinct prefixes across instances.
3. Choose a `KafkaTemplate` using the right factory and a manager controlling the transaction.
4. Select the boundary: `@Transactional`, `TransactionTemplate`, local transaction, or transactional listener container.
5. For consume–process–produce, ensure outputs and source offsets participate in the Kafka transaction.
6. Configure downstream consumers with `read_committed` when corresponding visibility is required.
7. Bound transaction duration and blocking operations.
8. Choose an appropriate recovery/rollback policy and do not swallow exceptions.
9. Protect external side effects with inbox/outbox or idempotency.
10. Monitor commits, aborts, fencing, transaction latency, and lag; test crash windows.

`KafkaTransactionManager` connects Spring's transaction infrastructure with Kafka producer transactions. It is especially useful when sending multiple Kafka records atomically or coordinating output records and source offsets in consume–process–produce flows. To achieve end-to-end reliability, combine clear transaction boundaries, unique producer identities, `read_committed` consumers, sound recovery, and idempotency whenever data leaves Kafka.
