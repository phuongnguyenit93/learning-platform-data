# Distinguishing Successful Delivery from Guarantees of a Single Business Effect

## 1. Three different outcomes commonly lumped together as "sent successfully"

In a messaging system, the phrase "the message was sent successfully" can refer to three different things:

1. **The producer managed to send the message:** the send call returns normally and the JMS provider accepts the send operation per the configuration/provider contract.
2. **The consumer received and acknowledged the message:** the broker delivers the message to the consumer and the acknowledgement or transaction completes.
3. **The business logic produced a committed effect:** the important data is recorded, for example an order changes state, a balance changes, or a payment instruction is accepted.

These three outcomes occur at different boundaries. The producer may succeed in sending the message while the consumer has not received it. The consumer may receive the message yet fail processing. The consumer may commit the database and then lose the connection before the JMS acknowledgement completes, causing the broker to redeliver the message.

Therefore, a `send()` API returning successfully does not prove the consumer finished processing; an acknowledgement does not prove every external side effect committed; and a message delivered only once does not by itself guarantee a business operation occurs only once.

In this lesson, **a single business effect** means that for the same logical event identifier, the system records the business change at most once in the system of record, even when the message is resent or redelivered. This is a goal you can design with idempotency and transactions; it is different from the promise that "the network delivers only one exact copy".

## 2. Boundaries in a JMS flow

A typical event flow has these steps:

~~~text
Producer service
    |
    | 1. send(eventId, payload)
    v
JMS provider / broker
    |
    | 2. deliver
    v
Consumer listener
    |
    | 3. validate + business processing
    v
Database transaction
    |
    | 4. commit business effect + inbox record
    v
Listener returns successfully
    |
    | 5. JMS acknowledgement / transaction commit
    v
Broker may remove message from pending delivery
~~~

Failure windows exist between steps. A process can stop, a connection can drop, or a transaction coordinator can return an undetermined result. A sound design must determine what happens if a failure occurs after each step.

| Boundary | What is confirmed | What is not yet confirmed |
| --- | --- | --- |
| `send()` returns normally | The provider accepted the send operation per provider semantics | The consumer received, processed, or committed the business operation |
| Broker delivers the message | The consumer/provider callback received the message | The consumer finished processing |
| JMS acknowledgement/commit | The provider can mark this delivery as confirmed | The database or an external API committed at the same time |
| Database commit | The data changes in the database transaction committed | The JMS acknowledgement committed or the next event was emitted |
| Consumer writes inbox and business data in the same transaction | The event ID and the database effect commit or roll back together | Side effects outside the database completed |

## 3. Producer send: success and undetermined outcomes

### 3.1. A successful send is not a consumer acknowledgement

A JMS producer sends a message to a `Destination` through `MessageProducer` or a Spring API such as `JmsTemplate`. When the send call returns normally, the producer knows the send operation completed under the contract of the API and provider. It receives no proof that the consumer has received or processed the message.

Spring `JmsTemplate` simplifies creating and releasing JMS resources. QoS attributes such as delivery mode, priority, and time-to-live can be configured on the template; for the values set by the template to actually override the provider's defaults, you must enable `explicitQosEnabled`. <Link ref="turn831759search2" title="Spring: Using JmsTemplate"/>

### 3.2. Persistent delivery is also not an exactly-once business effect

`DeliveryMode.PERSISTENT` asks the provider to store the message per the durability semantics of JMS/the provider. `NON_PERSISTENT` allows the provider to reduce storage overhead and accept a higher risk of losing messages when the provider fails.

Persistent delivery improves the chance that the message survives a broker failure, but does not prove the consumer processed it. It also does not coordinate the broker transaction with the business database. You also need to review storage configuration, replication, producer acknowledgements, and the provider's failure policy.

### 3.3. Retrying a send can create a business duplicate

Suppose the producer sends an `OrderPlaced` event to the broker. The broker received and stored the message, but the connection drops before the producer receives the result. The producer does not know whether the message was received or not.

If the producer retries with a new send call, the broker may receive an additional message with the same business meaning. This is not necessarily the provider creating a duplicate itself: the application emitted twice because the outcome of the first attempt was undetermined.

Jakarta Messaging specifies that a provider does not create a second copy of a message already acknowledged per provider semantics. Nevertheless, the specification also points out that a failure occurring between the commit/send and when the client receives the result can cause the application to produce functionally duplicate messages when it retries on its own. <Link ref="turn831759search3" title="Jakarta Messaging 3.1: acknowledgement and duplicate production"/>

**How to handle it:** create a stable `eventId` for a logical event before the first send. Every retry sending the same event must keep the same `eventId`. Do not create a new event ID just because the previous send timed out.

## 4. Consumer delivery and acknowledgement

JMS can redeliver a message when the consumer has not acknowledged it, a transaction rolls back, a Session recovers, or the connection/process fails. The consumer must therefore accept the possibility that the same message is processed multiple times.

The main mechanisms:

- `AUTO_ACKNOWLEDGE`: the provider acknowledges automatically at the point specified by the synchronous receive API or asynchronous callback.
- `CLIENT_ACKNOWLEDGE`: the application calls `Message.acknowledge()`; acknowledgement applies to messages delivered by the same Session, not only the single message being called on.
- `DUPS_OK_ACKNOWLEDGE`: the provider acknowledges lazily; the consumer must tolerate duplicates.
- `SESSION_TRANSACTED`: `commit()` acknowledges received messages and commits sent messages in the Session; `rollback()` recovers inputs and cancels the transaction's outputs.

In Jakarta Messaging, `JMSRedelivered` indicates the provider is marking the message as possibly delivered before. `JMSXDeliveryCount` is the delivery count reported by the provider; the first receipt has value 1, and a value of 2 or more indicates it has been redelivered. This is diagnostic metadata, not a business deduplication key. <Link ref="turn831759search3" title="Jakarta Messaging: JMSRedelivered and JMSXDeliveryCount"/>

Do not use `JMSMessageID` as a business event ID. The message ID is managed by the provider and may differ between two sends by the producer of the same logical event. A business `eventId` must be created by the application and kept stable across retries/replays.

## 5. Why does acknowledgement not guarantee a single business effect?

Consider a listener that updates the database and then lets the container acknowledge the message:

~~~text
1. Broker delivers OrderPlaced
2. Consumer updates database
3. Database COMMIT
4. Process stops before JMS transaction/ack completes
5. Broker redelivers OrderPlaced
~~~

On the second delivery, the consumer cannot just look at the message and assume it has not been processed. The database change already committed on the first attempt. If executed again, the order or balance could be updated twice.

The reverse direction can also happen if the database and JMS are not in the same transaction: the message is acknowledged while the database rolls back or does not commit. Then the broker does not redeliver the message even though the business operation was not recorded.

This is the dual-write problem: one business operation needs to update two independent resources, without a single atomic transaction spanning both.

Spring clearly explains that a local JMS transaction only covers receiving/sending through the JMS Session; database operations are an independent resource. When the database has committed but the JMS commit fails, the listener needs to detect duplicates. If a transaction coordinating multiple resources is needed, Spring supports configuring a JTA transaction manager with an XA-capable ConnectionFactory and suitable database resources. <Link ref="turn831759search0" title="Spring: Processing Messages Within Transactions"/>

## 6. Idempotency: processing the same event multiple times while producing only one effect

An idempotent operation is an operation whose business result is equivalent when executed repeatedly with the same logical input.

Examples:

- `setStatus(orderId, PAID)` can be idempotent if it only sets the state to `PAID`.
- `balance = balance + amount` is not idempotent if run again for the same event.
- `createInvoice(eventId)` is only idempotent if the database enforces a unique event ID or invoice key and a duplicate does not create a new invoice.

### 6.1. Stable event ID

Each logical event needs a unique ID, for example a UUID or a domain-generated ID. This ID is stored in the message payload or metadata and kept unchanged on retry.

Example payload:

~~~json
{
  "eventId": "evt-2026-000184",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "orderId": "ORD-184",
  "amountCents": 12500
}
~~~

The ID must identify one logical event, not one transmission through the broker. If the producer retries the event above, `eventId` remains `evt-2026-000184`.

### 6.2. Inbox/deduplication table

The consumer stores processed event IDs in an inbox table with a unique constraint. The inbox record and the business change must be committed in the same database transaction.

Example schema:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE business_order (
    order_id VARCHAR(100) PRIMARY KEY,
    total_cents BIGINT NOT NULL
);
~~~

`consumer_name` is included in the key so two different logical consumers can process the same event independently if required. If the event ID has already been processed by the same consumer, the unique constraint prevents writing to the inbox a second time.

### 6.3. Processing order inside the transaction

Inside one database transaction:

1. Try inserting `(consumer_name, event_id)` into the inbox.
2. If the insert violates the unique constraint, the event has already been processed; roll back the current transaction and return a duplicate result.
3. If the insert succeeds, apply the business change.
4. Commit the inbox record and the business data together.

If the business change fails, the transaction rolls back the inbox record as well. The broker can redeliver and the consumer retries. If the database commit succeeds but the JMS acknowledgement is lost, the event is redelivered; the inbox unique key recognizes the duplicate and the consumer does not apply the effect again.

Do not just `SELECT` from the inbox and then `INSERT` without a unique constraint. Two concurrent consumers could both see it does not exist yet and both apply the effect. The unique constraint is the final layer of protection; transactions and duplicate-key handling must be designed explicitly.

### 6.4. How long to keep the inbox?

Do not delete inbox records earlier than the period during which an event may be replayed or redelivered. If you delete the record and an old message is replayed, the effect may run again.

The retention policy must consider:

- Message and DLQ retention duration in the broker.
- Possibility of historical replay or backup restoration.
- Retry duration of producers and consumers.
- Audit requirements and retention regulations.
- Table size, indexes, and partitioning/archiving procedures.

For some domains, you can use a business key/version as the unique constraint instead of keeping an inbox indefinitely. Make sure that key truly represents an effect that is applied only once.

## 7. Transactional outbox: avoiding lost events between database and broker

The producer often has to both update the database and emit an event. If done as two separate operations:

- Database commits first, publish fails: the data changed but the event was not emitted.
- Publish first, database rolls back: the consumer sees an event for an uncommitted change.

A transactional outbox stores the event in the same database transaction as the business change.

~~~text
Producer transaction
    |
    +--> UPDATE business_order
    |
    +--> INSERT outbox_event(event_id, payload, status)
    |
    v
  COMMIT
    |
    v
Outbox publisher
    |
    +--> publish event to JMS
    |
    +--> mark outbox row as sent
    v
Consumer
    |
    +--> insert inbox event_id
    +--> apply business effect
    +--> commit database transaction
~~~

If the producer transaction rolls back, both the business update and the outbox row roll back. If it commits, the publisher can find unsent rows and continue after a process restart.

### 7.1. The outbox publisher can still emit again

The publisher may send the event successfully to the broker and then the process stops before marking the outbox row as `SENT`. On restart, the publisher sees the unsent row and publishes it again.

This is intentional at-least-once behavior. The publisher must keep `eventId` unchanged; the consumer's inbox/dedup protects the database effect from being applied twice.

### 7.2. Claiming and publishing safely with multiple publishers

If multiple instances read the outbox at the same time, you need a claim/lease mechanism or row locking to avoid processing the same row concurrently. You need to:

- Select a bounded batch.
- Mark a `PROCESSING` status or set a time-limited lease.
- Publish and verify the outcome according to provider semantics.
- Mark `SENT` only after publishing is confirmed per policy.
- Allow the lease to expire so another instance can take over if a publisher dies.
- Keep `eventId` stable across every retry.

Avoid holding a database lock while waiting long on the broker if possible. Design claiming/leasing, retry, and ordering to match the load and domain requirements.

Transactional outbox is a pattern for atomicity between a database change and recording the intent to emit an event. It does not by itself turn the broker into exactly-once and still requires an idempotent consumer. <Link ref="turn831759search7" title="AWS Prescriptive Guidance: Transactional outbox"/>

## 8. How do local JMS transactions, XA/JTA, and outbox differ?

| Mechanism | Coordinated resources | Main guarantee | Limitations |
| --- | --- | --- | --- |
| Local transacted JMS Session | JMS input and output in the same Session | Commits/rolls back received and sent messages together | Does not automatically include JDBC or HTTP |
| JDBC transaction | Changes on that database connection/resource | Business data and inbox/outbox rows commit together | Does not automatically commit the JMS broker |
| XA/JTA | Multiple XA resource managers enlisted in the same global transaction | Coordinator manages multi-resource commit/rollback | Requires XA-capable resources, transaction log, recovery, and more complex operations |
| Transactional outbox + idempotent inbox | DB transactions at producer and consumer, plus publisher/broker | Intent to emit events is not lost; consumer tolerates duplicate publish/delivery | Delivery is usually at-least-once; requires operating the publisher and retention |

### 8.1. Local JMS transaction

With a Spring listener container, `sessionTransacted=true` opens a local JMS transaction for each listener invocation. If the listener throws an exception out, message receipt is rolled back. Responses sent via the same `SessionAwareMessageListener` can belong to the same JMS transaction.

Database operations remain independent. If the database commits yet the JMS commit fails, the broker may redeliver; the consumer should have duplicate detection. <Link ref="turn831759search0" title="Spring: listener transaction semantics"/>

### 8.2. XA/JTA

XA/JTA can coordinate the database and JMS if both resources support XA and are properly registered with the transaction coordinator. This provides unified commit semantics but adds the cost of a transaction log, recovery, and the possibility of heuristic outcomes.

Do not use XA merely to avoid designing idempotency. Outbox/inbox is usually easier to deploy and operate in an independent-services architecture. If the business truly demands an atomic transaction across multiple resources, evaluate XA based on the actual provider, database, and infrastructure.

## 9. Exactly-once delivery and exactly-once effect

### 9.1. Exactly-once delivery

This is a claim about how many times a message is delivered over the transport. JMS has acknowledgements and transactions to manage delivery state, but failure windows can still create redelivery before the provider knows whether the message was confirmed.

The JMS specification requires that a provider does not redeliver a message that has already been acknowledged. However, a consumer can still receive an unacknowledged message again on failure; producer retries after an undetermined outcome can also create duplicate logical events.

### 9.2. Exactly-once business effect

This is a claim about how many times a business change is committed. With a stable event ID, the consumer can ensure the database effect is applied at most once by writing the inbox and business data in the same transaction with a unique constraint.

This does not mean the entire system executes every operation only once. A message may be sent and delivered multiple times; the handler may run multiple times; only the effect protected by the transaction/idempotency key is applied once.

### 9.3. External side effects

If the consumer calls a payment gateway, sends an email, calls an HTTP service, or writes a file, a database inbox transaction cannot automatically roll back external side effects.

For external APIs, use a domain-generated idempotency key if the provider supports it. Send the same key for every retry of the same logical operation. If the API does not support idempotency, you need a state model, reconciliation, and a compensation mechanism; you cannot infer exactly-once from JMS acknowledgement alone.

For example, record `payment_requested` in the database and emit a command via the outbox; the payment service calls the provider with the same idempotency key; then record the result in a separate transaction. Email may need a notification/outbox table with status and resend policy, though an email provider does not necessarily guarantee an email is delivered only once.

## 10. Ordering and concurrency also affect the business effect

Idempotency prevents the same event from producing duplicate effects; it does not by itself guarantee business ordering.

For example, `OrderCreated` and `OrderCancelled` can arrive in a different order if multiple consumers process in parallel, the publisher retries, or the broker does not guarantee ordering in the configuration in use.

Commonly used measures:

- Attach an aggregate ID and sequence/version to the event.
- Check the next sequence in the consumer transaction.
- Use optimistic locking or a version condition when updating.
- Partition/route the same aggregate to the same ordering key if the broker supports it.
- Do not assume multiple consumers on one queue always finish in send order.

Duplicate detection and ordering guards must work together: if event sequence 12 has already been processed while sequence 11 arrives late, the consumer needs a waiting, reject/retry, or reconciliation policy depending on the domain.

## 11. Retry, poison messages, and DLQ

Retry suits transient errors such as broker/database timeouts, network interruptions, or rate limits. It does not solve permanent data errors such as wrong schemas, missing required fields, or invalid events.

Retry design should include:

1. Classifying transient errors and permanent errors.
2. Increasing backoff and jitter to avoid multiple consumers retrying at the same time.
3. Limiting the number of redeliveries or total retry duration.
4. A DLQ for messages that cannot be processed after the retry policy.
5. Recording event ID, delivery count, exception type, and cause in logs/traces.
6. A procedure for fixing data or code and then replaying from the DLQ.

Do not skip a failing message by acknowledging it if the business operation has not completed and there is no compensation procedure. Conversely, infinite rollback can let a poison message occupy consumers and grow the backlog.

An idempotent consumer makes retries safer, but does not replace a retry policy. Make sure inbox retention covers the time a message may come back from the DLQ/replay.

## 12. Runnable example: an inbox table prevents applying the same event twice

The example uses Java 17, JDBC, and H2 to simulate an event delivered twice. Each processing attempt opens a database transaction; the inbox unique key and the business update commit together. The second delivery violates the unique key and does not increase the total amount again.

This example simulates the database/idempotency part of the consumer. It does not start a JMS broker; in a real application, call `handle(event)` from the listener and let the listener container acknowledge after the method completes successfully.

Project structure:

~~~text
jms-idempotent-consumer/
  pom.xml
  src/main/java/com/example/messaging/IdempotentConsumerDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-idempotent-consumer</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <h2.version>2.3.232</h2.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>${h2.version}</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/IdempotentConsumerDemo.java`:

~~~java
package com.example.messaging;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public final class IdempotentConsumerDemo {
    private static final String JDBC_URL =
            "jdbc:h2:mem:idempotency_demo;DB_CLOSE_DELAY=-1";

    private IdempotentConsumerDemo() {
    }

    private record OrderEvent(String eventId, String orderId, long amountCents) {
    }

    private enum Result {
        APPLIED, DUPLICATE
    }

    private static Connection openConnection() throws SQLException {
        return DriverManager.getConnection(JDBC_URL, "sa", "");
    }

    private static void initializeDatabase() throws SQLException {
        try (Connection connection = openConnection();
             Statement statement = connection.createStatement()) {
            statement.executeUpdate("CREATE TABLE inbox ("
                    + "event_id VARCHAR(100) PRIMARY KEY, "
                    + "processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
            statement.executeUpdate("CREATE TABLE business_orders ("
                    + "order_id VARCHAR(100) PRIMARY KEY, "
                    + "total_cents BIGINT NOT NULL)");
            statement.executeUpdate("INSERT INTO business_orders "
                    + "(order_id, total_cents) VALUES ('ORD-42', 0)");
        }
    }

    private static Result handle(OrderEvent event) throws SQLException {
        try (Connection connection = openConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement insert = connection.prepareStatement(
                        "INSERT INTO inbox (event_id) VALUES (?)")) {
                    insert.setString(1, event.eventId());
                    insert.executeUpdate();
                }

                try (PreparedStatement update = connection.prepareStatement(
                        "UPDATE business_orders "
                                + "SET total_cents = total_cents + ? "
                                + "WHERE order_id = ?")) {
                    update.setLong(1, event.amountCents());
                    update.setString(2, event.orderId());
                    if (update.executeUpdate() != 1) {
                        throw new SQLException("Order not found: " + event.orderId());
                    }
                }

                connection.commit();
                return Result.APPLIED;
            } catch (SQLException ex) {
                connection.rollback();
                if ("23505".equals(ex.getSQLState())) {
                    return Result.DUPLICATE;
                }
                throw ex;
            }
        }
    }

    private static long readOrderTotal(String orderId) throws SQLException {
        try (Connection connection = openConnection();
             PreparedStatement query = connection.prepareStatement(
                     "SELECT total_cents FROM business_orders WHERE order_id = ?")) {
            query.setString(1, orderId);
            try (ResultSet result = query.executeQuery()) {
                if (!result.next()) {
                    throw new SQLException("Order not found: " + orderId);
                }
                return result.getLong(1);
            }
        }
    }

    private static int inboxCount() throws SQLException {
        try (Connection connection = openConnection();
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("SELECT COUNT(*) FROM inbox")) {
            result.next();
            return result.getInt(1);
        }
    }

    public static void main(String[] args) throws Exception {
        initializeDatabase();

        OrderEvent event = new OrderEvent("evt-1001", "ORD-42", 125);
        System.out.println("firstDelivery=" + handle(event));
        System.out.println("redelivery=" + handle(event));
        System.out.println("effectTotalCents=" + readOrderTotal("ORD-42"));
        System.out.println("inboxRows=" + inboxCount());
    }
}
~~~

Run with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.IdempotentConsumerDemo
~~~

Stdout:

~~~text
firstDelivery=APPLIED
redelivery=DUPLICATE
effectTotalCents=125
inboxRows=1
~~~

What to observe:

- On the first attempt, the inbox insert succeeds; the business total increases by 125 cents; the two changes commit in the same transaction.
- The redelivery uses the same `eventId`; the unique primary key rejects the insert and the transaction rolls back; the business total does not increase further.
- `inboxRows=1` shows there is only one processing record for that event.

The demo uses in-memory H2 to run standalone and produce deterministic output. Data will be lost when the JVM stops; production needs a durable database, appropriate backups, a real unique constraint, and inbox retention aligned with the replay policy. With multiple concurrent consumers, the unique constraint remains the point of arbitration; the application must handle duplicate keys appropriately for the database in use.

## 13. Testing failure windows

Do not test only the happy path. Simulate at least the following scenarios:

| Failure point | Expected outcome | Protection mechanism |
| --- | --- | --- |
| Producer crashes before the outbox write transaction commits | Neither business update nor outbox row exists | Same database transaction |
| Producer crashes after commit, before publishing | Publisher finds the outbox row again and publishes later | Outbox polling/CDC |
| Broker receives event but publisher crashes before marking sent | Publisher may republish the same event ID | Consumer inbox/idempotency |
| Consumer crashes before database commit | Inbox and business update roll back; broker can redeliver | DB transaction + JMS rollback/ack policy |
| Database commit finishes, consumer crashes before JMS ack | Broker redelivers; inbox recognizes duplicate | Unique event ID in inbox |
| Consumers receive duplicates concurrently on two instances | Only one transaction inserts into the inbox successfully | Unique constraint and transaction |
| External API succeeds but response times out | Retry does not create a second side effect if provider supports key | External idempotency key and reconciliation |
| Poison event is retried many times | No infinite loop; moved to DLQ | Retry limit, backoff, DLQ |

Specifically test crashing after the business commit but before the acknowledgement. This is a failure window often missed when testing only a listener throwing an exception before committing.

## 14. Observability: measuring the right things

Do not lump every state into a single `messages_sent` metric. Track separately:

- Producer send attempts, send successes, send exceptions, and timeouts/ambiguous outcomes.
- Outbox pending count, age of the oldest record, publish retries, and time from DB commit to broker publish.
- Consumer deliveries, successful acknowledgements/commits, rollbacks, and redelivery count.
- Inbox duplicate count, unique constraint conflicts, and business effects applied.
- Listener processing latency, database transaction latency, and conversion/validation errors.
- Queue depth, message age, consumer lag, and DLQ depth.
- External API idempotency conflicts, timeouts, and reconciliation backlog.

Logs/traces should carry the same `eventId`, `correlationId`, aggregate ID, sequence/version, destination, and consumer name across producer, broker, and consumer. Do not log credentials or sensitive payloads.

An increasing duplicate metric does not necessarily mean the system is failing: it can be the normal result of retry/redelivery. What must be checked is whether duplicates cause the business effect to be applied multiple times.

## 15. Design checklist

1. What is `send()` confirming under the provider contract? Are there producer confirms or outbox states?
2. Do producer retries keep the `eventId` of the same logical event unchanged?
3. Does the message use a suitable delivery mode and broker durability?
4. Does consumer acknowledgement happen before or after the business commit?
5. Is the listener container using AUTO, CLIENT, DUPS_OK, or a transacted Session?
6. Is there a failure window between the database commit and the JMS ack?
7. Are the inbox record and the business update in the same database transaction?
8. Does the unique constraint protect the event ID when two consumers run concurrently?
9. Does inbox retention cover the retry, DLQ, and replay durations?
10. Does the producer use a transactional outbox when a database update must accompany event publication?
11. Can the outbox publisher publish duplicates, and can the consumer handle them?
12. Does the external API support an idempotency key? If not, what is the reconciliation/compensation approach?
13. Does retry have backoff, a limit, a DLQ, and a replay procedure?
14. Does per-aggregate ordering need a sequence/version guard?
15. Have crashes after commit but before acknowledgement and publish confirmation been tested?
16. Does the dashboard distinguish send, delivery, ack, DB commit, and business effect?

## 16. Key takeaways

Successful delivery and a single business effect are two different guarantees. A producer `send()` returning normally only confirms the send operation under the provider contract; it does not prove the consumer has processed it. JMS acknowledgements/transactions manage when the broker considers a message received, but do not automatically coordinate with a database or an external API. Retrying after an undetermined send outcome can create duplicate logical events; redelivery can cause a consumer to receive an unacknowledged message again. Attach a stable event ID, use an inbox unique constraint, and commit the inbox together with the business data in one database transaction. Use a transactional outbox to store the intent to emit an event alongside the business update; the publisher may send duplicates, so the consumer still needs idempotency. For side effects outside the database, use the provider's idempotency key or reconciliation. Design for each failure window and measure send, delivery, acknowledgement, database commit, and business effect separately.

### References

- [Jakarta Messaging 3.1 Specification — Message acknowledgement and duplicate delivery](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework 6.2 — Receiving a Message and Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2 — Using JmsTemplate and QoS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [AWS Prescriptive Guidance — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)