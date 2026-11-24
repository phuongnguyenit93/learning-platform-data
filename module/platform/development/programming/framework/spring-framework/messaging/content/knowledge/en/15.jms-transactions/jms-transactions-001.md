# Distinguishing Message Receipt Acknowledgement from Business Completion

> Goal: distinguish the moment the broker regards a message delivery as acknowledged from the moment the business operation is truly complete; understand acknowledgement modes and JMS transactions; design Spring listeners that stay safe when the database or a downstream system fails; apply idempotency, inbox/outbox, and test the failure windows.

## 1. Three Different Milestones in a Messaging Flow

In a JMS flow, the phrase "the message succeeded" can refer to three different events:

1. **Producer sent successfully:** the JMS provider has accepted the send operation according to the contract of `send()`/the transaction. This does not prove that a consumer has received or processed the message.
2. **Consumer acknowledgement:** the broker/provider records that the delivery of the message has been acknowledged. For a queue, the message usually no longer waits for another consumer to receive it, according to the provider's policy. This is a delivery state at the messaging layer.
3. **Business completion:** the required business changes have been persisted durably and the steps required by the business contract have reached a completed state.

The three milestones can occur at different times. A producer can send successfully while the consumer has not yet run. A consumer can acknowledge a message before writing to the database. The database can finish committing while the JMS transaction fails on commit, causing the broker to deliver the message again.

Therefore, **acknowledgement is a delivery confirmation at the broker layer; business completion is a business result that has been persisted and confirmed in the relevant systems.** Do not use one state to infer the other.

## 2. Message Processing Lifecycle and the Acknowledgement Point

A listener typically goes through these steps:

```text
Broker has a message
      |
      v
JMS consumer receives the message
      |
      v
Listener starts processing
      |
      v
Validate and perform the business operation
      |
      v
Commit the business changes
      |
      v
JMS acknowledge / commit session
      |
      v
Broker records the message as processed at the delivery layer
```

The diagram above shows the desired order when the database and JMS are managed separately: persist the business result first, then acknowledge the message. However, there is still a failure window between the two operations. If the database has committed but the JMS commit fails, the broker may redeliver the message. The listener must recognize an already processed message so that it does not repeat the side effects.

If the acknowledgement happens before the business result is persisted, the application can lose the message when the process stops between the two steps. If the acknowledgement happens only after the business result has committed, the system can receive a duplicate when the acknowledgement fails or the commit outcome is unclear. A reliable design must handle both situations.

## 3. What Do JMS Acknowledgement Modes Mean?

JMS provides three acknowledgement modes for a non-transacted session and one acknowledgement model based on transactions:

| Mode | How it acknowledges | Behavior on failure |
|---|---|---|
| `AUTO_ACKNOWLEDGE` | The provider acknowledges automatically according to JMS rules after `receive()` returns successfully or the invoked listener finishes successfully | The exact timing still depends on how the container executes; do not rely on the default mode of the Spring listener container to guarantee redelivery |
| `CLIENT_ACKNOWLEDGE` | The client calls `Message.acknowledge()` | A single acknowledge confirms all messages that the session has consumed before the call |
| `DUPS_OK_ACKNOWLEDGE` | The provider acknowledges lazily or in batches | Duplicates are possible when the provider/client fails; the consumer must tolerate repeated delivery |
| Transacted `Session` | `commit()` acknowledges the received messages and commits the messages sent in the same session; `rollback()` recovers the received messages and discards the uncommitted sent messages | A failing listener causes the transaction to roll back and the broker may redeliver |

According to the Jakarta Messaging specification, for synchronous `receive`, `AUTO_ACKNOWLEDGE` acknowledges when the receive call returns successfully. For an asynchronous `MessageListener`, the specification states that acknowledgement happens when the invoked listener finishes successfully. `CLIENT_ACKNOWLEDGE` is scoped to the session: calling `acknowledge()` on one message acknowledges the messages the session has previously delivered. `DUPS_OK_ACKNOWLEDGE` allows lazy acknowledgement, so duplicates can occur.

In Spring, pay attention to how the listener container executes. The Spring documentation warns that the default `AUTO_ACKNOWLEDGE` does not guarantee reliability: an error in the listener or a container shutdown can cause the message to be lost without being redelivered. With `DefaultMessageListenerContainer`, automatic acknowledgement can happen before the listener executes. Configure a transacted session when reliable processing is required.

Do not treat `CLIENT_ACKNOWLEDGE` as a database transaction. It only controls the acknowledgement of the messages belonging to one JMS session. If the session has received several messages, acknowledging one message can also acknowledge the earlier messages in the session; therefore you need to understand concurrency and how the container uses sessions.

## 4. What Does a JMS Transaction Acknowledge?

A transacted JMS session groups the send and receive operations belonging to the same session into a single unit of work:

- `commit()` acknowledges the messages received in the transaction and finalizes the messages sent in the transaction.
- `rollback()` discards the uncommitted sent messages and recovers the received messages so that the provider can deliver them again.

In a Spring listener container, set `sessionTransacted=true` so that each listener invocation runs in a local JMS transaction. If the listener completes normally, the container commits; if the listener throws an exception, the container rolls back and the message may be redelivered.

Example listener container configuration:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        return factory;
    }
}
```

The example uses `jakarta.jms`, which is suitable for Spring Framework 6/7. For Spring Framework 5, use the `javax.jms` namespace. `setSessionTransacted(true)` ties acknowledgement to the commit/rollback of the session. Concurrency should be set according to the capacity of the broker, the database, and the downstream services.

A listener can be declared with `@JmsListener`: 

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @JmsListener(
            destination = "orders.created",
            containerFactory = "ordersListenerFactory"
    )
    public void receive(OrderCreated event) {
        orderService.process(event);
    }
}
```

This example only shows the listener being bound to a factory with a JMS transaction. `OrderCreated` is a DTO and `orderService` is a business service provided by the application. If processing fails, the exception must propagate out of the listener so that the container rolls back the transaction; do not catch the exception and return normally if the work is not complete.

## 5. A JMS Transaction Does Not Automatically Commit the Database

This is the most important point when distinguishing acknowledgement from business completion. `sessionTransacted=true` only manages the JMS operations in the session. It does not automatically bring a JDBC/JPA transaction, Redis, an HTTP API, or the filesystem into the same transaction.

Suppose a listener performs two operations:

1. Update the order status in the database.
2. Commit the JMS session to acknowledge the message.

If the database commit succeeds but the JMS commit fails, the broker may redeliver the message. If the listener processes it again from the beginning, the order may be updated or paid twice. Conversely, if the message is acknowledged before the database commits and the application stops, the broker may not redeliver the message even though the business result has not been persisted.

Spring explicitly describes the case where database processing has committed but JMS processing has not: the listener needs duplicate detection. Therefore, using a transaction for each resource still requires an idempotency strategy at the business layer.

### Examples of Failure Windows

| Failure moment | Possible state | How to protect |
|---|---|---|
| The message is acknowledged before the DB commits, and the process stops | The broker does not redeliver; the business change does not exist | Use a transacted JMS session and commit after the listener completes |
| The DB commit finishes, the JMS commit has not succeeded | The broker redelivers; the business operation may run a second time | Inbox/deduplication key and idempotent business operations |
| The HTTP payment call succeeds, then the listener rolls back | The message is redelivered; the API may be called again | An idempotency key supported by the payment system, or a stateful outbox/workflow |
| The listener puts a task into an in-memory executor and returns | JMS may commit even though the task has not run; a process stop loses the task | Persist the job durably before returning, or use an outbox |
| The broker receives the outgoing message but the producer loses the response | The producer does not know whether the send succeeded | Use a stable event ID and have the consumer deduplicate |

## 6. Define Business Completion Before Acknowledging

"Business completion" must be defined according to the contract of each use case. For example:

- For an order-created event, completion may be that the order and its detail lines have been committed in the database.
- For a payment request, completion may be that the payment status has been confirmed by the provider and stored in the system.
- For an email-sending task, completion may be only that the email provider has accepted the request; that does not prove the email has reached the recipient's inbox.
- For a multi-step workflow, the listener may complete its own responsibility once it has written the `ACCEPTED` status and durably created the follow-up tasks. In that case, the final status should not be displayed as `COMPLETED` if downstream steps are still running.

Distinguish statuses such as `RECEIVED`, `ACCEPTED`, `PROCESSING`, `COMPLETED`, `FAILED`, and `REQUIRES_REVIEW` according to business needs. A JMS acknowledgement is delivery metadata; it does not replace the workflow status.

## 7. Idempotency: Handling Repeated Messages Without Repeating Side Effects

With at-least-once delivery, a message can be delivered multiple times when the listener rolls back, the connection is lost, or a commit has an unknown outcome. Idempotency ensures that processing the same request again does not create additional side effects beyond the desired result.

The producer should attach a stable `eventId` or `commandId` to the payload/property. The consumer uses that ID to recognize the same event across redeliveries. `JMSMessageID` can be used for tracing at the broker layer, but for business deduplication prefer an ID created by the application and kept stable across publishes/retries.

Commonly used approaches:

- Store processed event IDs in an inbox table with a unique constraint.
- Use a business key and a unique constraint to prevent creating duplicate records.
- Update the business status and record the event ID in the same database transaction.
- Use an idempotency key when calling an external API if the provider supports it.
- If a duplicate that has already been completed is received, return normally so that the JMS transaction can commit and the broker stops redelivering.

The `JMSRedelivered` header indicates that the provider has possibly delivered the message before; `JMSXDeliveryCount` indicates the delivery count according to the provider. These are observation signals and inputs for retry/DLQ decisions, not a replacement for a stable idempotency key. Do not use the delivery count as a business ID.

## 8. Inbox Pattern for Incoming Messages

The inbox pattern stores a marker for a processed message in the same transaction as the business change. When the broker redelivers after the database has committed, the consumer recognizes that the event ID already exists and does not run the side effects again.

An inbox table can be structured as follows:

| Column | Purpose |
|---|---|
| `event_id` | Stable ID from the producer, with a unique constraint |
| `event_type` | Type of the event |
| `received_at` | Time of receipt |
| `processed_at` | Time the processing step completed |
| `result_status` | Business result or processing status |

Processing flow:

1. Begin a database transaction.
2. Try to write the `event_id` into the inbox using an atomic operation with a unique constraint.
3. If the ID already exists and has been processed, skip the side effects and finish the listener successfully.
4. If the ID is new, apply the business change.
5. Write an outbox event if a follow-up event needs to be published.
6. Commit the database transaction.
7. The listener returns; the listener container commits the JMS transaction and acknowledges the message.

Spring pseudocode example:

```java
@JmsListener(
        destination = "orders.created",
        containerFactory = "ordersListenerFactory"
)
public void receive(OrderCreated event) {
    databaseTransaction.executeWithoutResult(status -> {
        // tryInsert must be atomic and based on the unique constraint of event_id.
        boolean firstDelivery = inboxRepository.tryInsert(event.eventId());
        if (!firstDelivery) {
            return; // Already processed: the listener finishes normally.
        }

        orderService.apply(event);
        outboxRepository.save(OrderProcessed.from(event));
    });
}
```

This is pseudocode illustrating the transaction boundary; `databaseTransaction` is a `TransactionTemplate` using the database's transaction manager, and `inboxRepository.tryInsert` must be implemented with an atomic insert statement and a unique constraint. Do not implement it as an `exists()` followed by `save()` without a unique constraint, because two consumers may both check before either one writes.

In the example, the database transaction commits before the listener method returns. Only then does the JMS transaction commit. If the process stops between the two commits, the broker may redeliver; the inbox recognizes the duplicate and the listener returns normally. As a result, the business change is not applied twice.

## 9. Outbox Pattern for Outgoing Messages

A business operation often both updates the database and needs to publish a message to another system. If you update the database and then send JMS directly, there are two failure windows:

- The database commit succeeds but the JMS send fails: the state has changed but the event is not published.
- The JMS send succeeds but the database rolls back: the consumer receives an event describing a change that does not exist.

The transactional outbox solves the problem by writing the business change and an outbox record in the same database transaction:

1. Update the business data.
2. Add the event to the outbox table.
3. Commit the database transaction.
4. A relay/publisher reads the outbox and sends the event to JMS.
5. After the send is confirmed according to the contract, the relay marks the record as published.

If the relay sends successfully but stops before marking the outbox, it may send the event again. The consumer still needs an inbox/idempotency. The outbox guarantees that the event is stored together with the business change and can be republished after a failure; it does not by itself create exactly-once delivery to every system.

## 10. When Do You Need JTA/XA?

If the requirement is that the JMS acknowledgement and the database commit must form one atomic transaction, you can use a JTA/XA distributed transaction:

- The listener container participates in an external transaction manager, usually `JtaTransactionManager`.
- The JMS provider must supply an XA-capable `ConnectionFactory` and be registered with the transaction coordinator.
- The database must use an XA datasource if the database update also needs to participate in the transaction.
- The transaction coordinator manages prepare/commit/rollback across the resources.

With XA, if one resource cannot commit, the coordinator can ask the participating resources to roll back according to the protocol. This reduces the window of inconsistency between JMS and the database, but increases complexity, transaction log cost, and the operational work of recovery.

Not every JMS provider supports XA; you cannot get an atomic transaction merely by placing `@Transactional` on the listener. Spring recommends considering a local JMS transaction together with duplicate detection if the system accepts controlled duplicate processing. Use XA when atomicity is truly required and the infrastructure fully supports it.

## 11. Retry, Redelivery, and Dead-Letter

Retry suits transient errors such as a database timeout or a downstream service temporarily losing its connection. Permanent data errors such as malformed JSON, an unsupported schema, or a business rejection should not be retried indefinitely.

An operational policy typically includes:

- Limit the number of retries or redeliveries.
- Use delay/backoff if the broker/provider supports it.
- Record the event ID, `JMSMessageID`, correlation ID, destination, delivery count, and exception.
- Move the poison message to a dead-letter queue or quarantine after a defined threshold.
- Provide a process for investigating, fixing the data, and replaying the message.

In Spring, when a listener throws an exception under `sessionTransacted=true`, the container rolls back the JMS session. The broker may redeliver according to the provider's policy. If the listener catches the exception and logs it without rethrowing, the container may consider the invocation successful and commit the message even though the business operation is not complete.

Do not use `JMSRedelivered` or the delivery count to decide that a side effect has definitely happened. They indicate delivery history, whereas the inbox/business key determines whether the business state has been committed.

## 12. Observing State and Tracing

To distinguish delivery from business, record two groups of information:

**Messaging layer:**

- Destination and consumer/listener ID.
- `JMSMessageID`, `JMSCorrelationID`, `JMSRedelivered`, `JMSXDeliveryCount`.
- Time of receipt, commit/rollback, retry, and DLQ.
- Queue depth, age of the oldest message, and consumption rate.

**Business layer:**

- Stable `eventId`/`commandId`.
- Business entity ID such as `orderId` or `paymentId`.
- Status `ACCEPTED`, `PROCESSING`, `COMPLETED`, or `FAILED`.
- Time of the database commit and the outbox publish.
- Failure reason and the related downstream system.

Use the correlation ID to join logs across multiple services; use the event ID to deduplicate; use the business ID to look up business state. These three IDs may coincide by system convention but serve different purposes.

Do not write the entire sensitive payload or secrets into logs. Metrics should distinguish the number of messages received, the number of successful listener invocations, the number of JMS commits/rollbacks, the number of completed business operations, and the number of messages entering the DLQ.

## 13. Testing the Acknowledgement Boundaries

Unit-testing the listener is not enough to prove reliable delivery. You need integration tests with an appropriate JMS provider or broker and a real database:

1. Listener succeeds: the database commits, the JMS transaction commits, and the message is no longer redelivered.
2. Listener throws an exception before the DB commit: the DB rolls back, JMS rolls back, and the broker redelivers.
3. The database commits successfully, then simulate a failure before the JMS commit: the message is redelivered but the inbox prevents repeated side effects.
4. A downstream message is sent successfully, then the relay stops before marking the outbox: the event is sent again but the downstream consumer deduplicates.
5. Send a message with the wrong schema: the listener fails according to the policy and the message eventually goes to the DLQ/quarantine.
6. Send two messages with the same event ID concurrently: the unique constraint allows only one transaction to process the business operation.
7. The broker restarts while the listener is processing: the uncommitted transaction is recovered or redelivered according to the provider.
8. The container shuts down during processing: an uncommitted message is not treated as business completion.

When testing failure windows, create a clear stopping point between the database commit and the JMS commit. Checking only the happy path will not reveal duplicate or message-loss errors at these two boundaries.

## 14. Common Design Mistakes

- **Treating broker acknowledgement as business completion:** a message can be acknowledged even though the database or downstream is not complete.
- **Using `AUTO_ACKNOWLEDGE` for flows that need reliability:** Spring warns that the default mode does not guarantee redelivery when the listener fails or the container stops.
- **Assuming `sessionTransacted=true` includes the database:** a local JMS transaction only manages the JMS operations in the session.
- **Using `@Transactional` and assuming JMS and the DB are atomic:** a suitable shared transaction manager or XA is required; two local transactions can commit independently.
- **Committing the database without an inbox:** redelivery can repeat side effects after the JMS commit fails.
- **Calling HTTP/payment in the listener without idempotency:** a rollback can cause the API to be called again.
- **Acking after merely pushing a task into an in-memory executor:** a process stop can lose work that has not been durably persisted.
- **Using `JMSMessageID` as the sole business key:** the provider ID is for tracing; the application's event ID is better suited for deduplication across publishes.
- **Catching the exception and returning normally:** the container can commit the message while the business operation is unfinished.
- **Assuming redelivery means the previous attempt definitely ran:** the broker can redeliver a message before the listener starts or after a failure that created no side effect.
- **Calling a running workflow `COMPLETED` as soon as the next step has been enqueued:** the business status must reflect the level of completion that was actually committed to.

## 15. Process for Designing a Reliable Listener

1. Define precisely the business completion of the use case and which statuses may be published to other systems.
2. Choose `sessionTransacted=true` or a suitable transaction manager for a listener that needs reliable redelivery.
3. Determine which resources are inside the JMS transaction and which have their own transactions.
4. Create a stable event ID and design the inbox/unique constraint for incoming messages.
5. Write the business change and the outbox event in the same database transaction if a follow-up message needs to be published.
6. Let the listener return successfully only after its durable responsibility is complete.
7. Design bounded retry, a DLQ, and a replay process.
8. If atomicity between JMS and the database is mandatory, evaluate JTA/XA with truly XA resources.
9. Test the failure points between the DB commit, the JMS commit, external APIs, and the outbox publish.
10. Monitor acknowledgement/rollback separately from business status and completion time.

## 16. Conclusion

Acknowledgement confirms the delivery of a message at the JMS layer. Business completion confirms that the business result has been persisted and has met the defined completion condition. These two milestones are protected together only when the transaction boundary correctly covers the resources, or when the application has a mechanism to handle the failure window.

With Spring JMS, `sessionTransacted=true` helps the listener roll back the message when processing fails and allows the broker to redeliver. A local database transaction remains independent, so you need an inbox/idempotency to prevent duplicates and an outbox to publish events after the data has committed. Use JTA/XA when atomicity across multiple resources is needed and the infrastructure supports it. Test the failure windows explicitly instead of only checking that the listener runs successfully.

## References

- [Jakarta Messaging 3.1 — Message acknowledgment and transactions](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)