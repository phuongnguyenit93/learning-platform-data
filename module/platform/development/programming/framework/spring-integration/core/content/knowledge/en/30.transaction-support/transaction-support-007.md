# Transactions with QueueChannel

## 1. Objectives and context

In the **Transaction support** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson explains how to design a flow that receives messages from a `QueueChannel`, processes them with an endpoint, and decides commit or rollback. The focus is on the relationship between channels, pollers, transaction managers, and storage resources; Java DSL is used to express the configuration.

After this lesson, you will be able to:

- Distinguish an in-memory queue from a queue backed by a transaction-capable message store.
- Place a transaction before the `receive()` operation to protect both message retrieval and business data changes.
- Determine the transaction scope across a `DirectChannel`, a subsequent queue, a gateway, or an executor.
- Explain how exceptions, filters, retries, and error handling affect whether a message remains available to be read again.
- Design tests that observe both queue state and database state simultaneously.

Running scenario: the application receives an order processing command, puts it into a queue, and has a consumer write the result into the `PROCESSED_ORDER` table. If the consumer finishes writing data but encounters an error before commit, we want **the written data rolled back and the command to remain in the queue for reprocessing**.

## 2. What does QueueChannel provide?

`QueueChannel` is a `PollableChannel`: producers call `send()`, and consumers actively call `receive()`, typically through a polling endpoint. It creates a buffer between sending speed and processing speed.

```java
QueueChannel orders = new QueueChannel(100);

boolean accepted = orders.send(
        MessageBuilder.withPayload("ORDER-101").build(), 0);
Message<?> received = orders.receive(0);
```

In this snippet, `100` is the capacity of the in-memory queue; `0` requests returning immediately instead of waiting. Check the `accepted` value and the `received == null` case. `send()` returning `true` only confirms that the channel accepted the message, not that the consumer's business processing succeeded. See [QueueChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/QueueChannel.html).

### 2.1. In-memory queues do not roll back automatically

With `new QueueChannel(100)`, taking a message out of the queue mutates an in-memory Java data structure. A JDBC transaction manager cannot restore that structure when rolling back the database.

Illustrative example, assuming `tx` is a `TransactionTemplate` managing JDBC:

```java
QueueChannel memoryQueue = new QueueChannel(100);
memoryQueue.send(MessageBuilder.withPayload("ORDER-101").build());

try {
    tx.executeWithoutResult(status -> {
        Message<?> message = memoryQueue.receive(0);
        if (message == null) {
            throw new IllegalStateException("No message to process");
        }
        jdbcTemplate.update(
                "insert into PROCESSED_ORDER (ORDER_ID) values (?)",
                message.getPayload());
        throw new IllegalStateException("Error after writing data");
    });
}
catch (IllegalStateException expected) {
    // JDBC rolls back; the in-memory queue has still lost the message.
}
```

Calling `memoryQueue.receive(0)` again will not return the retrieved message. Adding `@Transactional` to a service or `.transactional(...)` to a poller does not turn an in-memory queue into a rollback-capable resource.

### 2.2. Durability and transaction participation are two distinct properties

| Property | Question to answer |
| --- | --- |
| Buffering | Can the producer send before the consumer is ready? |
| Durability | Do committed messages survive process restarts or crashes? |
| Transaction | Do enqueue/dequeue operations commit or roll back together with business resources? |
| Safe replay (idempotency) | If the same command runs again, are business outcomes duplicated? |

A durable store can still be misused: if message retrieval already committed before the business transaction starts, a business error cannot restore the message. Conversely, the in-memory H2 database used in the later example supports rollback but does not preserve data across process death.

Spring Integration allows queues backed by a message store; with a transaction-capable store and a transactionally configured poller, removing a message only becomes permanent upon commit. See [Persistent QueueChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html#channel-configuration-queuechannel).

## 3. The right boundary: starting before receive()

A consumer must protect both removing the message from the store and the business updates:

```text
BEGIN consumer transaction
    receive() from QueueChannel backed by JDBC store
    synchronous validate / transform / route
    write business data using the same DataSource
COMMIT if all work inside the transaction succeeds
ROLLBACK if the transaction is marked for rollback
```

If `@Transactional` is placed only on the data-writing method, the sequence can become:

```text
receive() and delete message from store outside business transaction
    BEGIN service transaction
        write data
        error occurs
    ROLLBACK service transaction
```

The second transaction cannot undo work that already completed before it started. Therefore, for a consumer reading a queue, the poller is the right place to open a transaction wrapping `receive()` and synchronous downstream processing. This is the core reason for [Poller Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html#transaction-poller).

```mermaid
sequenceDiagram
    participant P as Producer
    participant Q as QueueChannel + JDBC store
    participant C as Transactional poller
    participant B as Business table
    P->>Q: send(command), commit enqueue
    C->>C: BEGIN consumer transaction
    C->>Q: receive()
    Q-->>C: command
    C->>B: INSERT result
    alt Processing succeeds
        C->>C: COMMIT
        Note over Q,B: Message deletion and result write commit together
    else Error before commit
        C->>C: ROLLBACK
        Note over Q,B: Message remains; result is not persisted
    end
```

`receive()` does not return a handle for the application to call `ack()` or `nack()`. In this design, the final state is governed by the store's transaction.

### 3.1. Producer and consumer usually have two separate transactions

Suppose the producer runs on an HTTP thread while the consumer runs on a scheduler:

```text
HTTP thread:      [Tx P: business update + enqueue] -- commit
Scheduler thread:                                 [Tx C: dequeue + process]
```

`Tx P` and `Tx C` are independent. An error on the consumer does not roll back the already committed HTTP transaction. If enqueuing uses the same JDBC resource as the producer's data, enqueuing can participate in `Tx P`; that still does not make `Tx C` a continuation of the same transaction.

In the standard JDBC model, transactional resources are bound to the thread. Synchronous endpoints can continue within the same scope; when processing moves to another thread, that scope does not propagate automatically. See [Transaction Boundaries](https://docs.spring.io/spring-integration/reference/transactions.html#transaction-boundaries).

## 4. Configuration example: QueueChannel backed by a JDBC store

The example uses Java 17 or later, modern Spring Integration Java DSL APIs, Spring JDBC, and H2. Select compatible Spring versions via your project's BOM or Spring Boot dependency management; do not mix library versions arbitrarily.

Required dependencies:

| Dependency | Purpose |
| --- | --- |
| `org.springframework.integration:spring-integration-core` | Channels, endpoints, Java DSL |
| `org.springframework.integration:spring-integration-jdbc` | JDBC channel message store and sample schema |
| `org.springframework:spring-jdbc` | `JdbcTemplate`, JDBC transaction manager |
| `com.h2database:h2` | Database for examples and tests |
| JUnit Jupiter, Spring Test if used | Running tests in a study project |

The Java blocks below correspond to illustrative files in package `example.integration`. They are presented in the lesson for learners to create in a practice project.

### 4.1. Payload serializable with default serialization

```java
package example.integration;

import java.io.Serializable;

public record OrderCommand(String orderId, boolean failAfterWrite)
        implements Serializable {

    private static final long serialVersionUID = 1L;
}
```

`failAfterWrite` is merely a deterministic failure toggle for the lab. In real business logic, failures might be deadlocks, timeouts, or constraint violations.

The JDBC channel store uses Java serialization by default. Therefore, payloads and header values to be persisted must be compatible with the serialization mechanism in use. Do not arbitrarily put connections, streams, or service objects into messages. Other serialization options require configuration matching your framework version; see [JDBC Channel Message Store Serialization](https://docs.spring.io/spring-integration/reference/jdbc/message-store-json.html).

### 4.2. Queue, store, and transaction manager infrastructure

```java
package example.integration;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.H2ChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableIntegration
public class QueueStoreConfig {

    @Bean(destroyMethod = "shutdown")
    public EmbeddedDatabase dataSource() {
        EmbeddedDatabase database = new EmbeddedDatabaseBuilder()
                .generateUniqueName(true)
                .setType(EmbeddedDatabaseType.H2)
                .addScript("classpath:org/springframework/integration/jdbc/schema-h2.sql")
                .build();

        new JdbcTemplate(database).execute("""
                create table PROCESSED_ORDER (
                    ORDER_ID varchar(64) primary key,
                    STATUS varchar(32) not null
                )
                """);
        return database;
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public JdbcChannelMessageStore orderMessageStore(DataSource dataSource) {
        JdbcChannelMessageStore store = new JdbcChannelMessageStore(dataSource);
        store.setChannelMessageStoreQueryProvider(
                new H2ChannelMessageStoreQueryProvider());
        store.setRegion("spring-integration-core-lab");
        return store;
    }

    @Bean
    public QueueChannel orders(JdbcChannelMessageStore orderMessageStore) {
        return new QueueChannel(
                new MessageGroupQueue(orderMessageStore, "orders-v1"));
    }
}
```

Key choices to note:

- `JdbcChannelMessageStore` is optimized for channels; choose the query provider matching your RDBMS. The H2 provider here is only for H2 databases.
- `MessageGroupQueue` connects the queue to the store. `orders-v1` is the logical queue's stable group ID; independent queues need distinct identifiers.
- `region` partitions data space in the store. When recovering a queue from a persistent database, reuse the exact same region, group ID, and table configuration.
- The same `DataSource` bean is passed into the store, `JdbcTemplate`, and the transaction manager.

See [JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html), [MessageGroupQueue API](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupQueue.html), and [DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html).

The actual sample schema resides in the JAR at `org/springframework/integration/jdbc/schema-h2.sql`, containing the `INT_CHANNEL_MESSAGE` table and related structures. Use the script matching your dependency version. In production environments, manage schemas using your project's migration tool rather than recreating tables when each instance starts; see [Spring Integration H2 schema](https://github.com/spring-projects/spring-integration/blob/main/spring-integration-jdbc/src/main/resources/org/springframework/integration/jdbc/schema-h2.sql).

H2 in this example is an in-memory database for observing transactions. To test recovery after process death, you need a disk-backed database or a database server configured to persist data.

### 4.3. Endpoint receiving messages via a transactional poller

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@Import(QueueStoreConfig.class)
public class OrderFlowConfig {

    @Bean
    public OrderWriter orderWriter(JdbcTemplate jdbcTemplate) {
        return new OrderWriter(jdbcTemplate);
    }

    @Bean
    public IntegrationFlow orderFlow(
            QueueChannel orders,
            OrderWriter orderWriter,
            PlatformTransactionManager transactionManager) {

        return IntegrationFlow.from(orders)
                .handle(orderWriter, "apply", endpoint -> endpoint
                        .id("orderConsumer")
                        .poller(Pollers.fixedDelay(500)
                                .receiveTimeout(0)
                                .maxMessagesPerPoll(1)
                                .transactional(transactionManager)))
                .get();
    }

    public static class OrderWriter {

        private final JdbcTemplate jdbcTemplate;

        public OrderWriter(JdbcTemplate jdbcTemplate) {
            this.jdbcTemplate = jdbcTemplate;
        }

        public void apply(OrderCommand command) {
            jdbcTemplate.update("""
                    insert into PROCESSED_ORDER (ORDER_ID, STATUS)
                    values (?, ?)
                    """, command.orderId(), "ACCEPTED");

            if (command.failAfterWrite()) {
                throw new IllegalStateException("Simulated error after INSERT");
            }
        }
    }
}
```

The poller opens a transaction before retrieving the message. `OrderWriter` runs synchronously on the polling thread and uses `JdbcTemplate` with the same `DataSource`, so the write operation joins the active transaction. You do not need to add `@Transactional` to `apply()` for this example to be transactional.

`fixedDelay(500)` is the polling schedule delay; `receiveTimeout(0)` avoids waiting for messages in the example; `maxMessagesPerPoll(1)` makes each processing turn easy to observe. These values are not default optimal settings for every system. `.transactional(transactionManager)` applies transaction advice to the polling task; see [PollerSpec API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/PollerSpec.html).

A common misconception: with a standard synchronous polling endpoint, increasing `maxMessagesPerPoll` does not mean all messages in one scheduled poll share a single transaction. The polling loop invokes the advised task once per receive-and-process cycle. If an atomic batch is required, design and verify it separately; see [AbstractPollingEndpoint source](https://github.com/spring-projects/spring-integration/blob/main/spring-integration-core/src/main/java/org/springframework/integration/endpoint/AbstractPollingEndpoint.java).

### 4.4. Sending messages and understanding the outcomes

In another bean, you can inject `QueueChannel orders` and send:

```java
OrderCommand command = new OrderCommand("ORDER-101", false);
boolean accepted = orders.send(MessageBuilder.withPayload(command).build());
if (!accepted) {
    throw new IllegalStateException("Channel did not accept the command");
}
```

For a successful command, the consumer commits: the queue no longer contains that message and the table has the `ORDER-101` row. For `new OrderCommand("ORDER-102", true)`, the processing run writes and then throws an error; rollback prevents the `ORDER-102` row from committing and the message can be retrieved again on the next poll.

Because the failure flag is inside the payload itself, `ORDER-102` will continue failing if there is no policy for handling poison messages. Do not use this pattern as an infinite retry mechanism in a real application.

If the producer wants to enqueue inside an explicit transaction, it can use `TransactionTemplate`:

```java
TransactionTemplate producerTx = new TransactionTemplate(transactionManager);
producerTx.executeWithoutResult(status -> {
    // Business JDBC updates can be performed here using the same DataSource.
    boolean accepted = orders.send(MessageBuilder
            .withPayload(new OrderCommand("ORDER-103", false))
            .build());
    if (!accepted) {
        throw new IllegalStateException("Enqueue failed");
    }
});
```

When using the JDBC store in the configuration above, enqueuing participates in the producer's transaction. An exception before commit can roll back adding the message. After commit, the consumer starts its own transaction when reading the message; the producer does not wait for and does not directly receive the consumer's processing result.

## 5. Correctly interpreting commit and rollback outcomes

The table below assumes no other consumer or automatic message-requeue policy interferes:

| Configuration | After a business error triggers transaction rollback | Business data state |
| --- | --- | --- |
| In-memory queue, JDBC transaction on poller | Retrieved message does not automatically return to the queue | JDBC writes in the transaction are rolled back |
| JDBC queue, transaction only on data-writing service | Message may have been deleted outside the service transaction | Service rolls back; queue is not restored by that transaction |
| JDBC queue and transactional poller, using same JDBC resource | Message retrieval is rolled back; message remains readable | Writes in the same transaction are rolled back |
| JDBC queue and transactional poller, processing completes normally | Message is deleted on commit | Writes in the same transaction are committed |
| JDBC queue and transactional poller, writing to a second uncoordinated database | Only resources in the transaction are rolled back | No atomicity guarantee between the two databases |

A transaction does not mean everything inside a method can be undone. An HTTP request already accepted by an external system, a sent email, or file operations are not automatically rolled back by JDBC.

For calling external services, one design is to insert the outbound work into an outbox table within the same JDBC transaction and let another worker send it. That worker still needs business keys and appropriate idempotent handling. This is a design recommendation for external side effects, not an automatic capability of `QueueChannel`.

## 6. Combining with other core components

### 6.1. DirectChannel and executors

```text
JDBC queue -> transactional poller -> transformer
           -> DirectChannel -> JDBC service
```

When all steps are synchronous, exceptions from the service can propagate back to the poller. If using the same managed JDBC resource, business updates and dequeueing can roll back together.

```text
JDBC queue -> transactional poller -> ExecutorChannel
                                    -> service on another thread
```

After the task is handed off successfully to the executor, the poller can commit without waiting for the service to finish. An error on the worker does not automatically restore the message in the input queue. Similarly, adding `@Async` or spawning threads inside a handler changes the scope that must be analyzed.

Do not conflate two configurations: an executor running **the entire polling task** can still allow the transaction to start on the polling thread; an `ExecutorChannel` placed **after receive** detaches downstream processing from that thread.

### 6.2. Two queues create two processing stages

```text
queue A -> poller A -> process A -> queue B -> poller B -> process B
```

If both JDBC queues use the same managed resource, transaction A can combine receiving from A, updating A's data, and adding to B. Transaction B handles receiving from B and B's data. An error in B does not roll back transaction A, which has already committed.

Therefore, durable handoffs between stages can be designed as sequential local transactions. They do not create a single transaction automatically spanning the entire asynchronous chain.

### 6.3. Transformers, routers, filters, and aggregators

- **Transformer:** if synchronous transformation throws an error and it propagates to the poller, the transaction can roll back. If it produces a new payload to store in the next queue, the new payload must also match that store's serialization.
- **Router:** the actual scope depends on the target channel. Synchronous branches and executor/queue branches have different handoff behaviors; looking at the router alone is not enough to determine the transaction.
- **Filter:** a message discarded along a normal processing path is not implicitly a transaction error. If the flow finishes normally, the dequeue can commit. Explicitly decide whether to discard, route to a discard channel, or treat the case as a failure.
- **Aggregator:** receiving a message and holding it until the group completes is a normal outcome. The input queue does not hold the entire group on behalf of the aggregator; storing group state requires its own store and recovery policy. `JdbcChannelMessageStore` serves channels, not as a replacement for an aggregator's generic store.

Example with invalid orders: if the requirement is to route them into a `rejectedOrders` queue, design that transfer as an intentional processing outcome. If the requirement is waiting for auxiliary data and retrying later, an explicit retry or delay mechanism is needed; a filter does not provide that by itself.

### 6.4. Gateways do not erase queue boundaries

A messaging gateway lets callers use a Java method API instead of manipulating messages directly. If the gateway sends into a queue for a consumer to process on another thread, method-call syntax does not carry the HTTP transaction over to the consumer. With a request-reply gateway, a caller timeout also does not prove that the consumer stopped or rolled back; track command status with a business identifier.

## 7. Exceptions, errorChannel, and repeatedly failing messages

### 7.1. Exceptions must reach the transaction boundary

A dangerous handling pattern:

```java
try {
    writeOrder(command);
}
catch (RuntimeException exception) {
    logger.warn("Failed to write order", exception);
    // Flow returns normally even though the business requirement did not complete.
}
```

If no component marks rollback, the transaction can commit after this catch block and consume the message. When failure must roll back, let the exception propagate or enforce an explicit rollback policy matching your design.

Spring's default rule rolls back on `RuntimeException` and `Error`; checked exceptions require configuration check. In an integration flow, the root error may be wrapped in a runtime `MessagingException`. Inspect the actual exception received by the transaction interceptor along with the active rules. See [Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html).

`@Transactional(rollbackFor = ...)` on a service does not replace poller configuration. Similarly, `REQUIRES_NEW` on a service can create an independent transaction, causing the service's committed writes to no longer roll back together with the dequeue. When custom rules are needed on the poller, pass a configured `TransactionInterceptor` into `.transactional(interceptor)`; see [TransactionInterceptorBuilder](https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/TransactionInterceptorBuilder.html).

### 7.2. ErrorChannel is the error-notification route

With a scheduled poller using standard error handling, errors from the task can be wrapped in an `ErrorMessage` and sent to an error channel. This route helps with logging, classification, and alerting; see [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Distinguish clearly:

- A handler catching an error and returning normally **before** the exception reaches the transaction interceptor can prevent the transaction from rolling back as intended.
- An outer error handler receiving an error that escaped the transactional polling task does not turn an earlier rollback into a commit.
- Sending an `ErrorMessage` for notification does not mean the original message was durably moved to a dead-letter queue.

Do not blindly write a flow that reads `errorChannel` and sends the original message back into the queue: if the dequeue already rolled back, the message is still in the store, so resending it can duplicate the command.

### 7.3. Rollback is not a complete retry policy

A rolled-back message remains in the store and can be polled again. Consequently, in the example, a payload with `failAfterWrite` always enabled will fail repeatedly. Applications must distinguish at least transient errors from unprocessable commands.

| Scenario | Design direction for the order example |
| --- | --- |
| Database temporarily unavailable | Retry with backoff, monitor message age |
| Command missing mandatory fields | Move to error queue or persist a durable rejected status |
| Same `orderId` sent a second time | Check existing outcome and apply idempotency decision |
| External service returns ambiguous result | Query by request key before repeating side effects |

If retry advice is used right inside the transaction and a JDBC error has already occurred underneath, the transaction may already be in an unusable state. The order of transaction advice and retry advice determines whether each attempt uses a new transaction or reuses the old one; do not add retry and assume the dequeue is properly protected.

If an attempt counter is updated inside the same transaction that always rolls back, the counter can also revert to its old value. A bounded retry policy needs appropriate state storage and commit boundaries.

Moving a failed message to another JDBC queue can be designed as the successful outcome of a transaction: take from the source queue, record error details, insert into the target queue, and commit together. If that transaction rolls back instead, adding to the error queue also rolls back. Avoid sending to an error queue in the same transaction and then throwing an exception expecting the message in the error queue to be kept.

## 8. What to test and at which layer?

Merely verifying that the handler throws an exception is not enough. Two critical observations are **whether the message remains available to read again** and **whether business data committed**.

### 8.1. Testing storage transactions deterministically

The JUnit 5 snippet below initializes only `QueueStoreConfig`, so no background consumer competes to pick up the message. It uses `TransactionTemplate` to test the same `receive()` + data-write scope. This tests the behavior of the store and transaction; it does not yet prove the endpoint/poller configuration works.

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.*;

class QueueTransactionTest {

    @Test
    void rollbackRestoresMessageAndUndoesBusinessInsert() {
        try (var context = new AnnotationConfigApplicationContext(
                QueueStoreConfig.class)) {
            var orders = context.getBean("orders", QueueChannel.class);
            var jdbc = context.getBean(JdbcTemplate.class);
            var tx = new TransactionTemplate(
                    context.getBean(PlatformTransactionManager.class));
            var writer = new OrderFlowConfig.OrderWriter(jdbc);

            assertTrue(orders.send(MessageBuilder
                    .withPayload(new OrderCommand("ROLLBACK-1", true))
                    .build()));

            assertThrows(IllegalStateException.class, () ->
                    tx.executeWithoutResult(status -> {
                        Message<?> message = orders.receive(0);
                        assertNotNull(message);
                        writer.apply((OrderCommand) message.getPayload());
                    }));

            assertEquals(0, count(jdbc, "ROLLBACK-1"));

            Message<?> availableAgain = orders.receive(0);
            assertNotNull(availableAgain);
            assertEquals("ROLLBACK-1",
                    ((OrderCommand) availableAgain.getPayload()).orderId());
            // This verification receive consumes the message from the test database.
        }
    }

    @Test
    void commitRemovesMessageAndKeepsBusinessInsert() {
        try (var context = new AnnotationConfigApplicationContext(
                QueueStoreConfig.class)) {
            var orders = context.getBean("orders", QueueChannel.class);
            var jdbc = context.getBean(JdbcTemplate.class);
            var tx = new TransactionTemplate(
                    context.getBean(PlatformTransactionManager.class));
            var writer = new OrderFlowConfig.OrderWriter(jdbc);

            assertTrue(orders.send(MessageBuilder
                    .withPayload(new OrderCommand("COMMIT-1", false))
                    .build()));

            tx.executeWithoutResult(status -> {
                Message<?> message = orders.receive(0);
                assertNotNull(message);
                writer.apply((OrderCommand) message.getPayload());
            });

            assertEquals(1, count(jdbc, "COMMIT-1"));
            assertNull(orders.receive(0));
        }
    }

    private int count(JdbcTemplate jdbc, String orderId) {
        return jdbc.queryForObject(
                "select count(*) from PROCESSED_ORDER where ORDER_ID = ?",
                Integer.class, orderId);
    }
}
```

Each test creates its own database thanks to `generateUniqueName(true)` and closes the database along with the application context. Do not wrap the entire test in an auto-rolling-back transaction: the state to observe is after the sample consumer transaction has finished.

### 8.2. Testing the real endpoint and poller

For `OrderFlowConfig`, add asynchronous tests covering the entire Java DSL configuration. Follow this sequence:

1. Start a context with the flow and prepare a test handler that allows blocking at a deterministic point using a latch.
2. Send the message and wait for a signal confirming the handler actually received it; do not use an arbitrary `sleep` as proof.
3. Let the handler complete or throw an exception per the scenario.
4. Wait for the transaction to finish and pause the consumer before inspecting the queue, preventing the next poll from consuming the message under observation.
5. Inspect both the business table and the message in the queue, then release latches and resources even if the test fails.

Scenarios to include in a practice project:

| Scenario | Expected observation |
| --- | --- |
| Handler succeeds | Business row exists; message is consumed |
| Error after INSERT | No business row; message remains readable |
| Producer enqueues then rolls back | New message does not exist after rollback |
| Same logic switched to in-memory queue | JDBC rolls back, but retrieved message does not return |
| Executor added after queue | Worker error does not automatically roll back already committed dequeue |
| Filter discards message along normal branch | Result matches the chosen discard policy |
| Restart with persistent database | Committed but unprocessed message can still be read |

Do not describe a restart test using two newly created H2 databases with different names: they do not share storage. Keep the same database, queue identifier, and serialization configuration for meaningful recovery testing.

The test blocks here are illustrative practice code, not claims that they were executed in the repository.

## 9. Idempotency and guarantee limits

Rolling back so messages can be retried is the foundation of recovery, and it simultaneously forces handlers to account for duplicate processing. Do not infer system-wide exactly-once guarantees solely because the queue uses JDBC transactions.

In the example, the `ORDER_ID` primary key prevents two result rows with the same ID. However, if a producer resends the same command after an already committed run, the second `INSERT` will fail; merely rolling back and polling again can leave the duplicate command stuck.

One way to extend the practice exercise:

1. Choose a business key representing a unique command, such as `commandId`; distinguish it from `orderId` if one order can have multiple valid commands.
2. Persist execution outcomes keyed by that ID in the same transaction as business data and the dequeue.
3. Upon receiving an already completed command, return the recorded outcome or complete as a successful consumption according to policy.
4. Use unique constraints and database-appropriate write statements to handle two concurrent consumers; a separate check-then-insert is insufficient.
5. For non-JDBC side effects, propagate idempotency keys or design reconciliation according to the target system's capabilities.

This is an enhancement suggestion for the order example. The `OrderWriter` code above intentionally demonstrates only transactions and does not yet implement a full idempotency policy.

## 10. Operational choices and diagnostics

Keep consumer transactions short: while a message is being processed, the transaction may hold a connection and database locks. Waiting on slow HTTP calls inside the same transaction increases resource hold time, even though HTTP calls are still not rolled back by JDBC.

With multiple consumers, verify the query provider's locking and SQL on the actual target database. Message retrieval order does not mean business completion order under concurrent processing. When a head-of-line message fails repeatedly, how much it blocks subsequent messages depends on queries and locking; do not assume every queue handles poison messages the same way.

Useful metrics for the order example are queued message count, oldest command age, rollback count, processing duration, failure count per command key, and count of commands moved to an error queue.

| Symptom | Hypothesis to check first |
| --- | --- |
| JDBC rolls back, yet command disappears | In-memory queue, `receive()` outside transaction, or wrong transaction manager |
| Queue retains command, yet data was written | Service uses an independent transaction, wrong resource, or side effect occurred outside JDBC |
| Same ID logged repeatedly | Poison message or duplicate key lacking a consumption policy |
| Error queue is empty despite send call | Adding to the error queue rolled back with the failed transaction |
| Old message missing after restart | Non-persistent database, changed group ID/region, or pointing to a different database |
| Low throughput when adding consumers | Long transactions, connection starvation, lock contention, or unsuitable SQL |

When diagnosing, note the channel implementation, store, thread, transaction manager, and commit/rollback timestamps for each stage. Matching bean names or similar-looking database URLs are not enough to prove operations shared a transactional resource.

## 11. Knowledge self-check

1. **Does adding `.transactional(transactionManager)` to the poller of `new QueueChannel(100)` recover messages after rollback?** No. A JDBC transaction does not undo an in-memory queue structure.
2. **Why is placing a transaction on the poller different from placing it only on the service method?** A poller can bring `receive()` into the transaction scope; a service starting afterward cannot protect an already completed dequeue.
3. **Does a filter returning a normal discard keep the message in the queue?** Not by default. Without a rollback, the message may be consumed and the transaction committed.
4. **Does a failing consumer roll back a producer's already committed transaction?** No. These are two stages with two separate transactions.
5. **Is resending the original message from an error handler always the right retry strategy?** No. If the dequeue rolled back, the message is already in the store; resending can duplicate the command.
6. **Does a JDBC queue automatically guarantee an email is sent only once?** No. Non-JDBC side effects require their own design.

When designing a flow yourself, mark every `send()`, `receive()`, thread handoff, and resource access location. For each transaction, explicitly identify which operations commit together, which roll back together, and which state enables safe replay.
