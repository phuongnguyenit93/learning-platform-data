# Kafka Transaction Boundaries

A Kafka transaction boundary is the scope of Kafka operations treated as a single unit of commit or rollback. When a transaction commits, records written inside the transaction become committed data for consumers reading in the appropriate mode. When a transaction aborts, those records are not visible to **read_committed** consumers. For consume-transform-produce flows, Kafka can also include the input record's offset in the same transaction as the output records.

The key point is defining accurately what this boundary covers. Kafka can guarantee atomicity for records and offsets within one Kafka transaction. It does not automatically extend that boundary to a database, HTTP API, filesystem, or another Kafka cluster. Spring Kafka provides mechanisms for applications to create and join Kafka transactions, yet the guarantee scope still depends on the transaction manager and how the listener container is configured.

## 1. What Does a Transaction Boundary Mean?

A Kafka transaction has a basic lifecycle:

1. The producer initializes or acquires a valid transactional producer.
2. The producer begins a transaction.
3. The producer sends one or more records, potentially across multiple topics and partitions.
4. The application commits the transaction if all work succeeds, or aborts if an error occurs.
5. Consumers using **isolation.level=read_committed** read only records belonging to committed transactions.

The boundary starts at beginning the transaction and ends at commit or abort. Sends issued inside this span belong to the same atomic unit. Sends outside this span are not folded into the transaction merely because they are invoked from the same Java method or the same request.

For example, an order-processing application may emit two events:

~~~
orders.created
orders.audit
~~~

If both sends sit inside the same Kafka transaction, Kafka can commit both or abort both. Consumers reading committed data will not receive half of the outcome from an aborted transaction. If the application sends the first event in transaction A and the second event in transaction B, the two sends have two independent boundaries and may yield different outcomes.

A Kafka transaction can span multiple partitions and multiple topics within the same Kafka cluster. It does not create a distributed transaction across multiple clusters. Reading across different partitions is also not a simultaneous global snapshot: consumers can receive records from different partitions in different poll calls, even when the records belong to the same committed transaction.

## 2. What Does Kafka Guarantee Inside a Transaction?

### 2.1. Atomic Writes Across Multiple Partitions

A producer can send records to multiple partitions and topics within one transaction. Kafka tracks transaction state via the transaction coordinator and internal markers. After the transaction commits, records are marked committed; after an abort, records are marked aborted.

Atomicity here refers to atomicity of transaction state and consumer visibility governed by the isolation level. It does not create a total order across partitions. Record order is still preserved within each partition in the order Kafka records it, while different partitions share no single global order.

### 2.2. Including Consumer Offsets in a Transaction

In a consume-transform-produce flow, the application can include processed offsets in the same transaction as output records using the **sendOffsetsToTransaction** API.

Example of what this operation means:

~~~
Read input record at offset 42
        |
        v
Compute result
        |
        +---- Send output event
        |
        +---- Send next offset (43) into transaction
        |
        v
Commit transaction
~~~

When the transaction commits, the output record and input offset are committed together. If the transaction aborts, neither the output record nor that offset is committed. The consumer group can therefore read the input record again to reprocess it.

When using the Kafka API directly, the application must pass the offsets along with consumer group metadata:

~~~java
producer.sendOffsetsToTransaction(
    offsetsToCommit,
    consumer.groupMetadata()
);
~~~

Do not call **consumer.commitSync()** or enable auto commit to substitute for this operation in an EOS flow. Doing so separates the offset commit from the Kafka transaction, breaking the atomic boundary.

### 2.3. Isolation Level Determines What Consumers See

Kafka consumers have two common read modes:

| Isolation level | Behavior |
|---|---|
| **read_uncommitted** | Can read records from both committed and aborted transactions. This is the Kafka consumer default. |
| **read_committed** | Returns only records belonging to committed transactions and non-transactional records. Records from aborted transactions are skipped. |

A **read_committed** consumer reads up to the partition's **Last Stable Offset (LSO)**. The LSO is the boundary at which preceding records have a settled transaction state. An open transaction can cause a **read_committed** consumer to wait before reading subsequent records in the same partition, even if those subsequent records were sent by another producer.

Therefore, if downstream relies on Kafka transaction atomicity, configuring consumers with **read_committed** is part of the design. Configuring a transactional producer alone is not enough for every consumer to share the same view.

## 3. Three Common Boundary Types

### 3.1. Write-Only Transaction

The application begins a transaction, sends multiple records, and commits. This transaction protects the Kafka writes belonging to it.

~~~
beginTransaction
    send(topic-A)
    send(topic-B)
commitTransaction
~~~

If commit succeeds, **read_committed** consumers can read both sets of records. If aborted, **read_committed** consumers receive none of the records in that transaction.

A write-only transaction does not automatically include a consumer's offsets. If the application previously read a message without sending its offset into the transaction, committing the producer transaction does not make consume and produce a single atomic unit.

### 3.2. Consume-transform-produce

This is the boundary commonly referred to when discussing Kafka Exactly-Once Semantics (EOS):

~~~
Consumer reads input
       |
       v
Application processes input
       |
       v
Producer sends output
       |
       v
Input offset + output records
       |
       v
Commit or abort same transaction
~~~

On success, Kafka commits both outputs and processed offsets. On failure, Kafka aborts outputs and leaves offsets uncommitted so input records can be read again. This prevents situations where the offset advanced without output being written, or output was committed while the offset remained uncommitted within the same Kafka flow.

In Spring Kafka, the listener container can manage this transaction. The container begins a Kafka transaction before invoking the listener, uses **KafkaTemplate** to send outputs within the active transaction, and then sends the processed offset into the transaction when the listener completes.

### 3.3. Transaction of a Publisher Service

A service can use **@Transactional** with **KafkaTransactionManager** to group Kafka sends inside a method into one transaction:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publish(OrderCreated event) {
        kafkaTemplate.send("orders.created", event.orderId(), event);
        kafkaTemplate.send("orders.audit", event.orderId(), event);
    }
}
~~~

This method establishes a boundary for Kafka sends participating in the specified transaction manager. When the method finishes normally, the transaction commits; when an exception triggers rollback, records in the transaction are aborted.

This boundary does not automatically include a consumer's offset. If the service is called from a listener without a container-managed Kafka transaction, the annotation on the service does not automatically turn the input offset into part of the transaction. To achieve consume-transform-produce EOS, configure transactions on the listener container or manage offsets manually with the appropriate Kafka API.

## 4. Transactions in Spring Kafka

Spring Kafka integrates Kafka transactions through **ProducerFactory**, **KafkaTemplate**, **KafkaTransactionManager**, and the listener container. These components must share the same **ProducerFactory** so **KafkaTemplate** participates in the active transaction properly.

### 4.1. Enabling the Transactional Producer

With Spring Boot, you can configure the transaction ID prefix in **application.yml**:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${spring.application.name:app}-${INSTANCE_ID:local}-
    consumer:
      properties:
        isolation.level: read_committed
~~~

When a transaction ID prefix is set, Spring Boot can auto-configure **KafkaTransactionManager** if the application has not declared one. If configuring **ProducerFactory** manually, set the transaction ID prefix on **DefaultKafkaProducerFactory** or the equivalent for your Spring Kafka version.

The prefix must be unique per running application instance. For example, two pods using the same prefix can contend for the same transactional ID. The broker fences the older producer when a new producer initializes with the same transactional ID; the older instance may receive **ProducerFencedException**. In multi-replica environments, include an instance or pod identifier in the prefix.

You can declare the transaction manager explicitly if the application needs control over the bean:

~~~java
@Bean
KafkaTransactionManager<String, Object> kafkaTransactionManager(
        ProducerFactory<String, Object> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Do not create a transaction manager with a different **ProducerFactory** than the factory used by **KafkaTemplate**. If the two components do not share a factory, sends may not join the transaction the application expects.

### 4.2. Transactions at the Listener Container

To run each listener execution inside a Kafka transaction, attach **KafkaTransactionManager** to the listener container factory. In recent Spring Kafka versions, the core configuration is:

~~~java
factory.getContainerProperties()
       .setKafkaAwareTransactionManager(kafkaTransactionManager);
~~~

Setter names may differ in older Spring Kafka versions; use the API matching your project's version.

The listener can emit output events as follows:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderCreated event) {
    BillingRequested result = createBillingRequest(event);
    kafkaTemplate.send("billing.requests", event.orderId(), result);
}
~~~

When the container is configured transactionally:

1. The container starts a Kafka transaction before invoking the listener.
2. **KafkaTemplate** uses the same **ProducerFactory** and joins the active transaction.
3. The listener completes normally; the container sends the processed offset into the transaction.
4. The container commits the transaction.

With a record listener, the boundary typically corresponds to processing one record. With a batch listener, the transaction spans the batch processed by the listener. Details of ack mode and container behavior depend on configuration; ensure the container is responsible for committing offsets via the transactional mechanism.

If the listener throws an exception and it propagates to the rollback mechanism, the transaction aborts. Kafka outputs are aborted and the input offset is not committed, so the record can be read again. If the listener catches the exception and returns normally, the container may view the run as successful and commit the transaction. When rollback is desired, let the error propagate or mark the transaction rollback-only appropriately.

### 4.3. Transactions on Methods Using **@Transactional**

**KafkaTransactionManager** can serve as the transaction manager for a service:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publishEvents(OrderCreated event) {
    kafkaTemplate.send("orders.created", event.orderId(), event);
    kafkaTemplate.send("orders.audit", event.orderId(), toAudit(event));
}
~~~

Points to keep in mind when using the annotation:

- Call the method through the Spring proxy so the transaction interceptor runs. Self-invocation within the same object normally bypasses the proxy.
- Specify the transaction manager explicitly when the application has multiple transaction managers, such as one for the database and one for Kafka.
- Sends must use a **KafkaTemplate** wired to the transaction manager's **ProducerFactory**.
- A publisher method's transaction includes only the Kafka operations participating in that transaction; it does not automatically pull consumer offsets or database operations into the same Kafka transaction.

Inside a listener that already has a container-managed transaction, sends via the matching **KafkaTemplate** join the active transaction. Avoid accidentally creating an independent inner transaction using an API that opens a new transaction, because those sends could then fall outside the boundary the container uses to commit offsets.

### 4.4. What Does **KafkaTransactionManager** Manage?

**KafkaTransactionManager** manages producer transactions. It does not by itself manage consumer lifecycles or offsets for every consumer in the application. The listener container supplies the needed integration: the container tracks processed records and sends offsets into the transaction upon commit.

Therefore, the following two setups differ:

| Configuration approach | Output records | Input offset |
|---|---|---|
| Service uses **@Transactional** with Kafka transaction manager | Can be inside the Kafka transaction | Not automatically included in the transaction |
| Listener container uses Kafka transaction manager | Can be inside the Kafka transaction | Container includes the processed offset in the same transaction |

This distinction determines whether the application achieves consume-transform-produce EOS or only transactional writes.

## 5. Transactions in Kafka and Exactly-Once Semantics

Kafka's Exactly-Once Semantics usually refers to processing a Kafka record, producing output records, and committing the input offset as one atomic unit. The goal is to avoid a retry producing a second committed Kafka output duplicating the prior attempt.

To achieve that goal, the flow needs the proper components:

1. A producer configured transactionally with a unique transactional ID per instance.
2. Output records sent within the transaction.
3. Input offsets sent into that very transaction.
4. Downstream consumers reading with **isolation.level=read_committed** if aborted outputs must be ignored.
5. Listener container or application code managing transaction and offset boundaries correctly.

Kafka enables the idempotent producer mechanism when using a transactional producer. Idempotence handles producer-layer retries to avoid duplicate writes caused by retries within a producer session under Kafka's supported conditions. Transactions extend this capability across multiple records and offsets. However, neither mechanism automatically prevents business logic from executing twice in a database or HTTP service.

Example: a listener reads **OrderCreated**, sends **BillingRequested**, and includes the input offset in the transaction. If the application fails before commit, the transaction aborts. When **OrderCreated** is read again, the new attempt can send **BillingRequested** in a new transaction. **read_committed** consumers only see the output of the committed transaction.

EOS has a specific scope: Kafka operations inside the transaction. It does not mean the entire distributed system, every service call, and every data mutation runs exactly once.

## 6. Kafka Boundaries Do Not Include Databases and External Services

A Kafka transaction is not an XA transaction and does not automatically create a distributed two-phase commit between Kafka and a database. **KafkaTransactionManager** and **DataSourceTransactionManager** manage two separate resources. Spring can synchronize the lifecycles of these transactions, yet synchronization does not turn them into an atomic transaction capable of rolling back all resources simultaneously in every scenario.

Consider a service that both updates a database and sends to Kafka:

~~~
Database transaction                  Kafka transaction
        |                                     |
        +---- UPDATE orders                   |
        |                                     +---- SEND OrderUpdated
        |                                     |
        +---- COMMIT                          |
                                              +---- COMMIT
~~~

If the database commit succeeds but the Kafka commit fails, the database has changed while the event has not been published. The application cannot roll back an already-committed database transaction simply by aborting the Kafka transaction. Reversing the commit order still leaves an inconsistent state in the opposite direction if the second resource fails.

Spring Kafka can participate in transaction synchronization when another transaction manager holds the primary transaction. This helps coordinate commit and rollback ordering under normal conditions, yet a failure window still exists between resource commits. Do not describe it as guaranteeing absolute atomicity between database and Kafka.

### 6.1. Use Transactional Outbox When Database and Event Guarantees Are Needed

When the business requirement is "if the database update succeeds, the event must reliably be publishable", Transactional Outbox is usually the right fit:

1. Within one database transaction, update business data and write a record to an outbox table.
2. A relay or CDC connector reads the outbox and publishes events to Kafka.
3. After publishing, the relay marks or records the entry as processed according to its mechanism.
4. Consumers use an event ID or business key for idempotent processing.

The database transaction guarantees business changes and the intent to emit an event are stored together. The relay may republish if stopped after publishing but before marking completion, so receivers still need to handle duplicates. Using CDC, such as Debezium, is one way to implement the relay; a polling publisher can also be used.

Outbox does not merge Kafka publishing and database updates into a single transaction. It turns the requirement into a recoverable process: event intent is persisted durably alongside data, while moving the event to Kafka can be retried safely.

### 6.2. HTTP APIs and Other Side Effects

Calling HTTP APIs, sending emails, writing files, or calling a payment service are outside Kafka transactions. If a listener calls an API successfully and then the Kafka transaction aborts, the input record can be read again and the API may be called a second time.

For external side effects, design idempotency keys, persist processing state, use outbox/inbox, or apply sagas and compensating actions when appropriate. Do not hold a Kafka transaction open while waiting on a long HTTP request without good reason: prolonged transaction duration raises the risk of timeouts, retries, and stalling committed reads on the affected partition.

## 7. Rollback, Retries, and Dead Letter Topic

When a listener container runs inside a Kafka transaction and the listener fails:

- The Kafka transaction is aborted.
- Output records in the transaction are aborted and ignored by **read_committed** consumers.
- The input offset is not committed in the transaction.
- The container can seek or let the record be read again according to the rollback and retry mechanism.

Spring Kafka provides **DefaultAfterRollbackProcessor** to control post-rollback behavior, such as retrying with backoff and recovering failed records. Once retry attempts are exhausted, the application can publish the record to a Dead Letter Topic (DLT). If moving the record to the DLT and committing the original offset must share the same transactional guarantee, configure the recoverer and after-rollback processor in the transactional mode appropriate for your Spring Kafka version.

Key decisions to clarify:

- **Infinite vs. bounded retries:** transient errors can be retried; unprocessable data errors usually need an attempt cap.
- **Backoff:** prevent tight retry loops from overloading brokers or dependent services.
- **DLT:** specify metadata to retain, such as original topic, partition, offset, exception, and processing timestamp.
- **Commit offset after recovery:** commit the original offset only after the record has been recovered per the chosen policy, e.g., successfully published to the DLT.
- **Exception handling:** if a listener swallows an exception and returns normally, the transaction may commit; distinguish handled errors from errors requiring rollback.

Do not assume "having a DLT" automatically means zero message loss. The outcome depends on how DLT sends happen, the transaction around recovery, and when the original offset is committed.

## 8. Transaction Size and Duration

Transactions should wrap the exact unit of work that must commit together. Too-small transactions can increase overhead; too-large transactions increase how long open state is held and widen rollback scope.

Operational factors include:

- **Transaction timeout:** transactions must finish within the producer's **transaction.timeout.ms** and the broker's maximum allowed limit (**transaction.max.timeout.ms**). Producer requests exceeding the broker limit will be rejected.
- **Listener processing duration:** avoid long waits for HTTP, database, or external calls while a Kafka transaction is open.
- **Batch size:** large batches can increase throughput but increase the amount of work rolled back together and transaction completion latency.
- **Producer cache:** Spring Kafka reuses transactional producers. If there are many concurrent transactions or nested transactions, configure caching and suffix capacity appropriately so producers are not exhausted.
- **Instance identity:** each instance needs its own transaction ID prefix to avoid fencing one another.
- **Consumer visibility:** long-open transactions can hold back the LSO and make **read_committed** consumers wait.

Do not increase timeouts just to mask a hung transaction or an overly slow listener. Find why the transaction is not finishing on time before raising limits.

## 9. Example Tracing Success and Failure

Suppose a listener reads **orders** at partition 2, offset 42 and emits **billing.requests**.

### Successful Commit Case

~~~
1. Container begins transaction T1
2. Listener reads orders-2@42
3. KafkaTemplate sends billing.requests
4. Container adds offset 43 of orders-2 to T1
5. T1 commits
~~~

Result:

- The **billing.requests** record in T1 becomes visible to **read_committed** consumers.
- Offset 43 is committed for the consumer group.
- When the consumer restarts, it resumes from the committed offset per group rules.

### Listener Failure Before Commit Case

~~~
1. Container begins transaction T2
2. Listener reads orders-2@42
3. KafkaTemplate sends billing.requests
4. Listener throws exception
5. T2 aborts
6. Container handles rollback and rereads record per retry policy
~~~

Result:

- The **billing.requests** record in T2 is not visible to **read_committed** consumers.
- Offset 43 is not committed in T2.
- The input record can be reprocessed.

If the listener updated a database or called an HTTP API before throwing the exception, those side effects do not roll back automatically with T2. That is why transaction boundaries must be drawn per resource, rather than inferred from operations sitting inside the same method.

## 10. Common Configuration Errors

| Symptom | Possible cause | What to check |
|---|---|---|
| **No transaction is in process** when sending via **KafkaTemplate** | ProducerFactory is transactional but the send is not running inside a transaction, or the template does not join the active transaction | Check transaction manager, proxy, execution thread, and the ProducerFactory used by the template |
| **ProducerFencedException** | Two producer instances share the same transactional ID/prefix, or an old producer was fenced | Generate a unique prefix per instance; check producer lifecycle and initialization |
| Consumer receives aborted records | Consumer uses **read_uncommitted** | Set **isolation.level=read_committed** for consumers that must skip aborted records |
| Output is not atomic with input offset | Listener container is not configured transactionally, or offsets are committed separately | Check the container's Kafka transaction manager and offset commit mechanism |
| Database changed but event is missing | Database and Kafka have two independent transactions; failure happened between commits | Consider Transactional Outbox and idempotent processing |
| **read_committed** consumer stalls despite new records | An earlier transaction in the partition is still open or lacks a settled state | Check hung transactions, timeouts, and the producer owning the transaction |
| Record is reprocessed after rollback | Offset was not committed, so retry is expected behavior | Design idempotent handlers and side effects; review retry/DLT policy |

## 11. Transaction Boundary Design Checklist

Before implementation, answer these questions:

1. Which unit of work needs to commit or abort together: a single publish, a record listener, or a batch?
2. Which topics and partitions does the transaction span? Are they in the same Kafka cluster?
3. If doing consume-transform-produce, is the input offset sent into the same transaction as outputs?
4. Which consumers need **read_committed** to see only committed outputs?
5. Do **KafkaTemplate**, **KafkaTransactionManager**, and the listener container share the same **ProducerFactory**?
6. Does every application instance have its own transaction ID prefix?
7. What happens when the listener throws an exception, exhausts retries, or fails to publish to the DLT?
8. Are there database operations or external side effects in the same method yet outside the Kafka transaction?
9. If coordinating a database and Kafka, is outbox/inbox or a saga safer than relying on transaction synchronization?
10. Are transaction duration and size small enough to avoid timeouts and LSO stalls?

A solid design clearly describes where the boundary starts, where it ends, which data commits together, and how recovery works when commit fails. In Spring Kafka, choosing **KafkaTransactionManager** is only one part; you must configure the listener container, offset handling, and consumer isolation level properly to achieve the desired guarantee.
