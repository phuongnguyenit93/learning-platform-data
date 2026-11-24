# At Most Once, At Least Once, and Exactly Once

In Kafka, the three terms **at most once**, **at least once**, and **exactly once** describe how many times a record or a processing effect can be recorded when the system encounters failures, retries, restarts, or consumer rebalances. They are *delivery/processing semantics*, not three quality levels that can be toggled by a single property.

With Spring Kafka, you need to clearly define the guarantee at each stage: the producer sending the record, the broker storing the record, the consumer reading the record, the application executing business logic, and the consumer committing the offset. A pipeline only achieves an end-to-end guarantee when all relevant stages coordinate properly.

## 1. Putting Guarantees in the Right Scope

A Kafka processing flow typically looks like this:

~~~text
Source application
    |
    | KafkaTemplate.send(...)
    v
Kafka topic / partition
    |
    | poll() and invoke @KafkaListener
    v
Consumer application
    |
    +---- update database
    |
    +---- call external service
    |
    +---- send record to another topic
    |
    v
Commit consumer offset
~~~

There are three separate questions:

1. **Can the producer drop or duplicate a write?** This depends on broker acknowledgements, retries, and an idempotent producer.
2. **Can the consumer skip or reprocess a record?** This depends on when the offset is committed relative to when processing occurs.
3. **Can the business effect happen multiple times?** This depends on where the effect is stored and how the application handles duplicates.

An offset is the position a consumer group has processed within a partition. If the offset has been committed, a restarted consumer typically resumes from the next position. If processing completed but the offset was not committed, the record may be read and processed again. This is a common source of duplicates in the at least once model.

| Guarantee | Observed number of processing runs/effects | Main risk |
|---|---:|---|
| At most once | 0 or 1 | Records or business logic may be lost/skipped |
| At least once | 1 or more | Duplicate processing may occur |
| Exactly once | Exactly 1 within the protected scope | Only holds within the transaction scope and participating systems |

Do not infer that a producer using acks=all makes the entire application exactly once. Producer acknowledgement only concerns the broker confirming the record write; it does not automatically combine database updates or consumer offset commits.

## 2. At Most Once — Processing at Most Once

At most once means each record is processed **no more than once**. A record may be processed once or not processed at all. The system prioritizes avoiding duplicates, accepting the possibility of data loss when errors occur.

### How It Works

The consumer commits the offset before running business logic. If the application stops right after the commit, Kafka considers the record processed and will not redeliver that record to the consumer group. As a result, the business logic may never have run.

~~~text
1. Consumer receives record 42
2. Consumer commits the next offset (43)
3. Application starts processing record 42
4. Process stops abruptly
5. Consumer restarts from offset 43
6. Record 42 is not reprocessed
~~~

Another way that can lead to similar behavior is enabling auto commit and allowing the offset commit to happen before the listener finishes its work. In that case, a shutdown or error at an unfortunate moment can cause a record to be skipped.

### Spring Kafka Configuration

If you intentionally choose auto commit, the configuration might look like this:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: true
      auto-commit-interval: 1s
~~~

With Spring Kafka, check your container configuration and the Spring Kafka version in use: the listener container usually manages offset commits and disables auto commit by default unless the application explicitly enables it. When choosing at most once, you must understand exactly who commits and at what point.

You can explicitly express the intent to commit before business logic using manual acknowledgement:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual_immediate
~~~

~~~java
@KafkaListener(topics = "telemetry", groupId = "telemetry-fast")
public void consume(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    // Commit offset before running business logic.
    acknowledgment.acknowledge();

    process(record.value());
}
~~~

With MANUAL_IMMEDIATE, calling acknowledge on the consumer thread requests an immediate commit. You need to configure and verify the appropriate commit mode if the application changes how listeners are executed.

### Pros and Limits

At most once is suitable when some messages can be skipped without significant consequences, such as high-frequency telemetry, instantaneous metrics, or state updates that can be superseded by newer samples. It can reduce reprocessing overhead and avoid repeating an action.

Do not use this approach for payments, order creation, inventory deduction, transaction recording, or any business operation that requires every event to be processed. A skipped record can produce incorrect business data with no automatic retry to recover.

## 3. At Least Once — Processing at Least Once

At least once ensures the system keeps trying to process until a successful processing attempt is confirmed. A record may be processed once or multiple times. This is a common choice for Kafka consumers because it prioritizes not losing events.

### How It Works

The consumer only commits the offset after the listener processes successfully. If processing fails, the offset is not committed and the record can be redelivered. However, there is an important window: the business logic has completed, but the offset commit has not yet succeeded.

~~~text
1. Consumer receives record 42
2. Listener processes record 42 successfully
3. Database is updated
4. Process stops before offset 43 is committed
5. Consumer restarts from offset 42
6. Listener processes record 42 again
~~~

Kafka cannot automatically know that the database already executed the business logic in step 3. Therefore, the second processing run can create duplicates if the application has no deduplication mechanism.

### Spring Kafka Configuration

For a listener processing one record at a time, you can use the RECORD acknowledgement mode:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

~~~java
@KafkaListener(topics = "orders", groupId = "billing")
public void onOrder(OrderCreated event) {
    billingService.apply(event);
    // When the listener returns successfully, the container commits the record's offset.
}
~~~

If the listener throws an exception, the container can route the record through the configured retry and error handler mechanism. The offset is only committed according to the container's error-handling and recovery policy. You must clearly design the retry count, backoff, dead-letter topic (DLT), and what counts as recovered.

### Making Business Logic Idempotent

At least once is usually combined with **idempotency**. An idempotent operation can be executed multiple times with the same event while producing a final business outcome equivalent to executing it once.

Each event should have a stable identifier, such as eventId. The consumer records this identifier together with the business update in the **same database transaction**:

~~~java
@Transactional
public void apply(OrderCreated event) {
    boolean firstDelivery = processedEventRepository
            .insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        // The event was already applied previously; redelivery produces no new side effect.
        return;
    }

    billingRepository.createInvoice(event.orderId(), event.amount());
}
~~~

Here, insertIfAbsent represents an insert operation with a unique constraint on event_id; the concrete implementation depends on the database. Recording the event and updating the invoice must commit or roll back together. If the two operations are in two independent transactions, the application can still end up in an inconsistent state.

Other ways to prevent duplicates:

- Use eventId as an idempotency key when calling external APIs, if the API supports it.
- Use a unique business key, such as orderId + operationType, to prevent creating the same effect twice.
- Use an upsert or an update that sets the final value rather than incrementing, if the business semantics allow it.
- Store processing state and results in the same transaction as business data.

Checking only an in-memory variable or temporary cache is not sufficient to prevent duplicates across restarts, rebalances, or multi-instance deployments.

### Producer and At Least Once

On the producer side, the application needs to handle send results and send failures. Configuring acks=all, appropriate retries, and an idempotent producer improves reliability when writing to Kafka. However, the application still needs to observe send results and handle cases where sending fails or times out.

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
~~~

acks=all requires the broker to acknowledge across all replicas currently in the ISR (in-sync replicas). Combine this with an appropriate min.insync.replicas on the broker/topic to avoid accepting writes when the number of synchronized replicas falls below the desired level.

An idempotent producer prevents duplicate records arising from retries within the same producer session via Kafka's sequence mechanism. It does not automatically recognize two independent send() calls by the application as the same business event.

## 4. Exactly Once — One Effect Within a Defined Scope

Exactly once means a record produces exactly one observed effect within the scope covered by the guarantee mechanism. With Kafka, transactions can combine writing output records with committing input offsets in a single Kafka transaction.

The key point is that **exactly once in Kafka does not mean exactly once across all systems outside Kafka**. If a listener updates a database, makes an HTTP call, or sends a command to another system, a Kafka transaction does not automatically roll back those side effects.

### What Does a Kafka Transaction Protect?

Suppose a consumer reads from the orders topic, processes the record, and writes the result to orders-enriched. A Kafka transaction can combine the following two operations:

1. Writing output records to the destination topic.
2. Committing the offsets of the processed input records.

~~~text
Start Kafka transaction
    |
    +--> Read record from orders
    |
    +--> Process record
    |
    +--> Write record to orders-enriched
    |
    +--> Include input offset in transaction
    |
    +--> Commit transaction
             |
             +-- Success: output and offset are committed together
             |
             +-- Failure: transaction is aborted
                         output is not visible to read_committed
                         input offset is not committed
~~~

If the application stops before the transaction commits, the input record will be read again. Output records from an aborted transaction are not visible to consumers using read_committed. Thus, reprocessing can produce a valid output without exposing the output of the failed transaction.

### Producer and Consumer Configuration

The producer needs a transactional ID prefix. Each application instance must have a unique prefix to prevent producer instances from accidentally fencing each other. Spring Boot can be configured as follows:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-instance-01-
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

In this example, orders-instance-01- is an illustrative value. When running multiple replicas, generate a unique prefix per instance according to your deployment setup. Spring Kafka uses this prefix to create transactional producers. Do not share the same prefix across independent instances.

Consumers reading transactional data should use isolation.level=read_committed. If read_uncommitted is used, the consumer can read records belonging to uncommitted or aborted transactions, causing the application to observe unconfirmed data.

### Binding Kafka Transactions to the Listener Container

Spring Kafka provides KafkaTransactionManager. The listener container needs to use this transaction manager so that the transaction wraps record processing. A KafkaTemplate using the same ProducerFactory will participate in the active transaction on the listener thread.

~~~java
@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean(name = "kafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String> kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            KafkaTransactionManager<String, String> transactionManager) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties()
                .setKafkaAwareTransactionManager(transactionManager);

        return factory;
    }
}
~~~

The listener can send results to another topic:

~~~java
@Component
public class OrderEnrichmentListener {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEnrichmentListener(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(topics = "orders", groupId = "order-enrichment")
    public void onOrder(String orderPayload) {
        String enriched = enrich(orderPayload);
        kafkaTemplate.send("orders-enriched", enriched);
    }

    private String enrich(String payload) {
        return payload + "|enriched";
    }
}
~~~

When the listener container is configured with a Kafka transaction manager, the container begins a transaction before invoking the listener. Sends via KafkaTemplate participate in that transaction. When the listener completes successfully, the container adds the input offset to the transaction and commits. If the listener throws an exception, the transaction is aborted; the error handler and retry policy determine the next processing attempt.

The example above illustrates a consume-transform-produce flow. In a real application, keep the same producer factory for both the transaction manager and KafkaTemplate, configure serializers/deserializers matching the data types, and verify that the listener container uses the right factory with the transaction manager.

### Exactly Once with Kafka Streams

If the application uses Kafka Streams instead of custom listeners, you can configure the processing guarantee:

~~~properties
processing.guarantee=exactly_once_v2
~~~

Kafka Streams manages transactions for reading, processing, and writing results according to the Streams model. You must configure a stable application ID, ensure brokers support the corresponding feature, and ensure internal topics are created/configured appropriately. This is specific to Kafka Streams; it does not replace configuring transactions for a standard Spring Kafka listener.

## 5. Limits When Business Logic Involves Databases or External Services

A Kafka transaction can atomize Kafka operations within the transaction. It cannot automatically include a PostgreSQL/MySQL transaction, an HTTP call to a payment gateway, or an operation on an external system.

For example:

~~~text
Consumer receives OrderCreated
    |
    +--> Write invoice to database: COMMIT succeeds
    |
    +--> Send Kafka output
    |
    +--> Kafka transaction ABORT
~~~

The database already saved the invoice, but the Kafka transaction failed. Kafka redelivers the event and the consumer may create the invoice again. Adding @Transactional to the method does not automatically turn a database transaction and a Kafka transaction into a single atomic distributed transaction. Two different transaction managers can still commit or roll back at different times.

Two design patterns are commonly used:

### Inbox or Processed Events Table

The consumer stores eventId in a table with a unique constraint in the same database transaction as the business changes. When Kafka redelivers the event, the duplicate insert is detected and the consumer skips the already-applied effect. This is a common way to achieve at least once delivery while maintaining a single business effect in the database.

### Transactional Outbox

If a database transaction needs to both update data and emit an event, the application writes the business data and an outbox row in the same database transaction. A relay process or CDC reads the outbox and sends the event to Kafka. If the relay resends because it did not record the acknowledgement, the receiving consumer should still be idempotent.

~~~text
Database transaction
    |
    +--> Update business tables
    |
    +--> Insert outbox event
    |
    +--> Commit
             |
             v
      Outbox relay / CDC
             |
             v
           Kafka
~~~

Outbox solves the gap between updating the database and publishing the event. It does not make every external consumer automatically exactly once; the receiving side still needs to handle duplicates safely.

## 6. Comparison by Failure Scenario

| Scenario | At most once | At least once | Kafka exactly once (consume-transform-produce) |
|---|---|---|---|
| Process stops before processing | The record may already be committed and lost | Offset is uncommitted so it can be read again | Transaction aborts; input can be read again |
| Process stops after processing, before offset commit | If offset was committed earlier, it will not rerun | May reprocess and create duplicates | Output and offset share a transaction so aborted output is not exposed |
| Broker temporarily unavailable | May be skipped depending on commit timing | Retries and handles send/receive errors | Transaction may abort or retry per configuration |
| Database committed but Kafka offset uncommitted | Record may be lost if offset was committed early | May update the database again | Kafka transaction does not roll back the database |
| Producer retries the same send | May be lost if no retry | May produce duplicates without idempotence | Idempotent producer and transaction protect Kafka writes within their scope |

This table describes general behavior. Specific outcomes also depend on retry policy, error handler, acknowledgement mode, commit mode, transaction timeout, listener type, and the system storing business effects.

## 7. Which Model to Choose?

| Need | Recommended choice | What to implement |
|---|---|---|
| Telemetry that can tolerate loss, prioritizing no repeats | At most once | Commit before processing; accept possible loss |
| Business events that must be processed and can be retried | At least once | Commit after processing; idempotency at the consumer |
| Reading from Kafka, transforming, and writing to another Kafka topic | Kafka exactly once | Transactional producer, transaction-enabled listener container, offsets in transaction, output consumer using read_committed |
| Reading from Kafka and updating a database | At least once + idempotent database operation | Event ID, unique constraint, database transaction |
| Updating a database and publishing an event | Transactional outbox | Write outbox in the same database transaction, relay/CDC, idempotent consumer |
| Processing a Kafka Streams topology | Kafka Streams exactly once | processing.guarantee=exactly_once_v2 and appropriate Streams configuration |

In many business systems, the practical choice is at least once combined with idempotent processing. This approach is easy to observe and recover while maintaining reliability across consumer restarts or rebalances. Exactly once via Kafka transactions is especially useful when both input and output stay within Kafka. For databases or external APIs, design idempotency or outbox/inbox patterns around actual transaction boundaries.

## 8. Configurations and Behaviors to Verify

**Consumer offset**

- Disable auto commit when you want the listener container to control commit timing.
- Choose RECORD for per-record listeners when committing after each record; choose batch mode when listeners process batches and understand the commit scope.
- With manual acknowledgement, clearly decide between MANUAL and MANUAL_IMMEDIATE, which thread calls acknowledge, and how the container performs commits.
- Do not commit offsets before business logic completes if at least once is required.
- Test behavior during rebalance, shutdown, and slow listener processing.

**Producer and broker**

- Choose acks=all and min.insync.replicas according to durability requirements.
- Enable the idempotent producer to protect producer retries.
- Configure retries, delivery.timeout.ms, and explicit send error handling; do not treat calling send() as proof the broker has acknowledged the record.
- Monitor ISR, under-replicated partitions, and producer errors.

**Transaction**

- Each application instance needs a unique transactional ID prefix.
- Consumers reading transactional data need read_committed if they must not see uncommitted or aborted records.
- Keep transactions short enough; long processing can exceed the transaction timeout.
- Handle ProducerFencedException and transaction errors according to instance lifecycle; do not infinitely retry a fenced producer.
- Confirm that KafkaTemplate and the listener container use compatible producer factory and transaction manager beans.
- Monitor transaction aborts, commit timeouts, and consumer lag in operations.

**Retry and dead-letter topic**

- Retries can cause the same event to be processed multiple times; business logic must tolerate that.
- A DLT helps preserve unprocessable records for investigation or recovery. Moving a record to the DLT and committing the offset must follow a clear policy.
- If partition ordering must be preserved, consider the impact of retry topics, non-blocking retries, and sending records to a DLT.
- Do not treat moving a record to the DLT as successful business processing; establish monitoring and replay procedures.

## 9. Common Misconceptions

1. **An idempotent producer means end-to-end exactly once.** False. It protects producer retries; it does not prevent two independent sends and does not protect database updates.
2. **acks=all means consumers never process duplicates.** False. Producer acknowledgement does not determine when the consumer commits offsets.
3. **Committing offsets after the listener means no duplicates.** False. The process can stop after business logic finishes but before the offset is committed.
4. **A Kafka transaction includes the database because the listener has @Transactional.** False. Check which transaction manager governs each operation; a Kafka transaction does not automatically roll back an independent database transaction.
5. **Enabling read_committed is enough for exactly once.** False. It only controls which transactional records the consumer reads; the producer and listener must still participate in transactions properly.
6. **More retries mean a stronger guarantee.** Retries increase the chance of success but also increase the chance of repeated processing. Combine retries with idempotency, retry limits, and recovery procedures.

## 10. Design Checklist

Before choosing a guarantee for a Spring Kafka flow, answer these questions:

- If a record is not processed, what is the business impact?
- If the same record is processed twice, could it create duplicate charges, invoices, or notifications?
- Is the offset committed before or after the listener completes?
- Does the listener use record, batch, or manual acknowledgement?
- Does the producer check send results, retries, and idempotence?
- Is output data in the same Kafka transaction as the input offset?
- Do consumers reading transactional data set read_committed?
- Do external databases/APIs have idempotency keys, inbox, or outbox patterns?
- Are retry, DLT, rebalance, and shutdown behaviors clearly defined?
- Are metrics and logs sufficient to detect duplicates, skipped records, transaction aborts, and consumer lag?

A reliable design clearly states the guarantee at each boundary, commit timing, transaction scope, and duplicate-handling strategy. Once those conditions are defined, the team can choose at most once for loss-tolerant data, at least once for events requiring recovery, or Kafka exactly once for consume-transform-produce flows contained entirely within Kafka.
