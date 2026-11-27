# Receive and forward in one transaction

## 1. Goals and real-world scenario

In the **Poller transaction** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson explains how to place receiving a message and forwarding a message inside the same transaction. The focus is on the relationship among `Message`, `MessageChannel`, polling endpoints, and Java DSL when building an integration flow that can recover from failures.

Suppose a system receives order-processing requests into an `orders.in` queue and then forwards them to `orders.ready`. For each message, we want to uphold this rule:

> Confirm removing a message from the source only when handing it off to the destination within the chosen scope also succeeds.

If the process fails after receiving but before handing off, the message must remain eligible for redelivery. If the hand-off has committed, the message must not still appear at the source as an unforwarded request.

This lesson uses two queues stored in the same database to illustrate this rule. This is a practice model for transactions; choosing a queue technology for a production system also depends on load, operational requirements, and available infrastructure.

After this lesson, you will be able to:

- Identify which operation a transaction must start before.
- Distinguish forwarding to a channel from completing business logic at a downstream consumer.
- Configure a transactional poller using Java DSL.
- Explain the conditions under which rollback restores source state.
- Build test scenarios verifying commit, rollback, and asynchronous boundaries.

## 2. What are the receive and forward steps?

In a polling consumer, the endpoint actively calls `receive()` on a `PollableChannel`. When a message is available, the endpoint passes the message to a handler; the handler can process it and send it onward through an output channel.

| Component | Role in this lesson |
| --- | --- |
| `Message<?>` | Carries the payload and headers of the order request |
| Input `PollableChannel` | The source from which the polling endpoint pulls messages |
| Poller | Defines the schedule, receive limit, and applied advice |
| Endpoint | Connects the input channel to the handler |
| `BridgeHandler` | Forwards messages without altering the business payload |
| Output `MessageChannel` | The next hand-off point in the flow |
| Transaction manager | Manages transactions for the configured resource |

A messaging bridge fits when the goal is simply to connect two channels. If format transformation is needed, use a transformer as the first endpoint and attach the poller to that endpoint. The Java DSL structure of a bridge is documented in [Messaging Bridge](https://docs.spring.io/spring-integration/reference/bridge.html).

Interpret "forward succeeded" accurately:

- Sending to a standard `DirectChannel` invokes the registered handler on the same calling thread. When the handler returns normally, that synchronous processing has finished.
- Sending to a queue confirms only the enqueue step per that queue's mechanism. A consumer pulling the message later has its own processing lifecycle.
- Sending across an asynchronous boundary does not mean all downstream work has completed.

Therefore, before configuring transactions, describe the hand-off point to protect as a concrete action: writing the message to the destination queue, updating a business table, or calling a synchronous consumer.

## 3. The transaction must cover receive

### 3.1. Failure window when protecting only business processing

Consider this flow:

~~~text
receive from source
    ↓
call service with @Transactional
    ↓
forward to destination
~~~

If the receive operation is already confirmed independently, a transaction inside the service cannot reach back to protect that earlier receive. For example:

1. Message `order-1042` is removed from the source.
2. The service opens a transaction and updates data.
3. Sending to the destination encounters an error.
4. The service's transaction rolls back.
5. The source may still have lost the message.

`@Transactional` on a service is useful for the service's scope, but you must check where that transaction starts relative to `receive()`.

### 3.2. Required scope

With a transactional poller, the desired structure is:

~~~text
BEGIN
    receive from a transaction-capable source
    perform required synchronous processing
    forward to a transaction-participating destination
COMMIT

If an error matches rollback rules:
ROLLBACK changes on participating resources
~~~

What makes a poller special is that transaction advice can wrap the `receive()` operation itself rather than starting only at a downstream processing call. This is the purpose presented in [Poller Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html#transaction-poller).

~~~mermaid
sequenceDiagram
    participant P as Polling endpoint
    participant T as Transaction manager
    participant I as Source JDBC queue
    participant O as Destination JDBC queue

    P->>T: Begin transaction
    P->>I: receive()
    I-->>P: Message
    P->>O: send(Message)
    alt Succeeds until commit
        P->>T: Commit
        Note over I,O: Source deletion and destination insertion take effect together
    else Error requiring rollback before commit
        P->>T: Rollback
        Note over I,O: Source is restored; new destination record is discarded
    end
~~~

The diagram assumes both queues use the same JDBC resource managed by the transaction manager. It does not depict an automatic transaction spanning arbitrary external systems.

## 4. Four conditions for meaningful atomicity

### 4.1. The source must support rolling back the receive operation

By default, `QueueChannel` stores messages in memory. Having a JDBC transaction on the poller does not cause removals from an in-memory queue to be undone.

When a `QueueChannel` is backed by `JdbcChannelMessageStore`, message retrieval modifies JDBC data. If it participates in the right transaction, rollback can restore that data. This mechanism is described in [Configuring Message Channels — Persistent QueueChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

The question to ask is "does the resource performing receive participate in the transaction?", rather than merely checking whether `transactional(...)` appears in the configuration.

### 4.2. The transaction manager must manage the right resource

In the two-JDBC-queue example, the store and the transaction manager both receive the same `DataSource` bean. `DataSourceTransactionManager` manages transactions for a single JDBC `DataSource`; classes like `JdbcTemplate` obtain connections via Spring's transaction-participation mechanism. See [DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html).

Two connections opened independently or two separate `DataSource` instances pointing at the same database do not automatically form one shared transaction.

If a flow both receives from JMS and writes to JDBC, analyze the two resources separately. Choosing a JDBC transaction manager alone does not make JMS receive an atomic part of the JDBC transaction.

### 4.3. Protected steps must sit within an appropriate execution scope

In the synchronous transaction model under consideration, the transaction context is bound to the thread. Handlers chained via `DirectChannel` can continue using that context; this still requires compatible resources and propagation.

When a message is placed into a queue for another consumer to pull, or dispatched to another executor, processing beyond that boundary does not automatically inherit the current transaction. The [Transaction Boundaries](https://docs.spring.io/spring-integration/reference/transactions.html#transaction-boundaries) documentation explains this limit.

### 4.4. Failures must lead to a rollback decision

An error that is caught and turned into a normal return can cause the transaction wrapper to treat the work as successful. Conversely, an exception unwinding out of the transaction advice is evaluated against rollback rules.

Under Spring's typical defaults, `RuntimeException` and `Error` trigger rollback; checked exceptions require matching rollback rules. In Spring Integration, exceptions from handlers may also be wrapped in `MessagingException`, so inspect the actual exception reaching the transaction interceptor. See [Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html).

## 5. Java DSL example: moving between two JDBC queues

### 5.1. Preparing for the practice exercise

The example uses the following dependencies, with versions aligned via the project's BOM or dependency management:

- `spring-integration-core`.
- `spring-integration-jdbc`.
- `spring-jdbc` and `spring-tx`.
- H2 for the practice environment.
- JUnit Jupiter and `spring-test` if using the test snippet in a later section.

The application classes below can be placed in the same package. Java DSL uses `IntegrationFlow.from(...)`.

The example chooses H2 to stay focused on transactions. When switching databases, change both the schema script and the corresponding `ChannelMessageStoreQueryProvider`. The JDBC store requires tables to be initialized before the endpoint runs; [JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html) documents schemas and query providers per database.

### 5.2. DataSource for the lab environment

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;

@Configuration
public class JdbcLabConfiguration {

    @Bean
    public EmbeddedDatabase dataSource() {
        return new EmbeddedDatabaseBuilder()
                .generateUniqueName(true)
                .setType(EmbeddedDatabaseType.H2)
                .addScript("classpath:org/springframework/integration/"
                        + "jdbc/store/channel/schema-h2.sql")
                .build();
    }
}
~~~

H2 here is an in-memory database. It lets you observe JDBC commit and rollback, but it does not demonstrate preserving data across JVM shutdowns. To practice recovery after restarts, use a disk-backed database and keep queue identifiers stable.

### 5.3. Store, channels, and transactional poller

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.H2ChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableIntegration
public class ReceiveForwardConfiguration {

    @Bean
    public PlatformTransactionManager receiveForwardTxManager(
            DataSource dataSource) {

        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public JdbcChannelMessageStore channelStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);

        store.setChannelMessageStoreQueryProvider(
                new H2ChannelMessageStoreQueryProvider());

        return store;
    }

    @Bean
    public QueueChannel incomingOrders(JdbcChannelMessageStore channelStore) {
        return new QueueChannel(
                new MessageGroupQueue(channelStore, "orders.in"));
    }

    @Bean
    public QueueChannel readyOrders(JdbcChannelMessageStore channelStore) {
        return new QueueChannel(
                new MessageGroupQueue(channelStore, "orders.ready"));
    }

    @Bean
    public IntegrationFlow receiveAndForward(
            PlatformTransactionManager receiveForwardTxManager) {

        return IntegrationFlow.from("incomingOrders")
                .bridge(endpoint -> endpoint
                        .id("receiveForwardBridge")
                        .autoStartup(false)
                        .poller(Pollers.fixedDelay(500)
                                .receiveTimeout(0)
                                .maxMessagesPerPoll(1)
                                .transactional(receiveForwardTxManager)))
                .channel("readyOrders")
                .get();
    }
}
~~~

Both queues share `channelStore` but use different group IDs: `orders.in` and `orders.ready`. A group ID is the store's persistence key for the queue, not a message header name. Keep IDs stable when data must be reused across runs; this requirement is noted in [MessageGroupQueue API](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupQueue.html).

`transactional(receiveForwardTxManager)` sits on **the bridge's poller**, because the bridge receives from a pollable input channel. `PollerSpec` provides this method to add transaction advice to the polling task. See [PollerSpec API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/PollerSpec.html).

`autoStartup(false)` lets the exercise control when the endpoint starts running. In production when automatic startup is desired, omit this setting or set it to `true`.

### 5.4. Running the flow and observing results

~~~java
import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class ReceiveForwardDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                JdbcLabConfiguration.class,
                ReceiveForwardConfiguration.class)) {

            PollableChannel incoming = context.getBean(
                    "incomingOrders", PollableChannel.class);

            PollableChannel ready = context.getBean(
                    "readyOrders", PollableChannel.class);

            Message<String> order = MessageBuilder
                    .withPayload("order-1042")
                    .setHeader("businessKey", "order-1042")
                    .build();

            if (!incoming.send(order)) {
                throw new IllegalStateException("Unable to write to source queue");
            }

            Lifecycle bridge = context.getBean(
                    "receiveForwardBridge", Lifecycle.class);
            bridge.start();

            Message<?> forwarded = ready.receive(5_000);

            if (forwarded == null) {
                throw new IllegalStateException(
                        "Message not yet received at destination queue");
            }

            System.out.println(forwarded.getPayload());
        }
    }
}
~~~

The expected output is the payload `order-1042`. The demo explicitly consumes the message from the destination queue to print it; therefore, once the demo finishes, the destination no longer holds that read message.

String payloads and String headers help the example avoid complex serialization issues. When persisting domain objects into a persistent store, ensure the serialization/storage strategy supports the payload and any headers that must be preserved.

### 5.5. What changes does the transaction make?

For an input message that has been persisted successfully, the desired states can be interpreted as follows:

| Moment | Source queue | Destination queue |
| --- | --- | --- |
| Before poller processes | Contains `order-1042` | Empty |
| Inside transaction after receive and send | Deletion pending completion | Insertion pending completion |
| After successful commit | Empty | Contains `order-1042` |
| After rollback before commit | Restored | No new record from the failed transfer |

The "inside transaction" row describes changes belonging to the in-flight transaction. Whether another thread sees the data or blocks depends on database isolation levels and locking mechanics.

The hand-off protected in this configuration is **persisting the message into `readyOrders`**. If another consumer receives from `readyOrders` and fails while processing, that is a failure in the next unit of work. It does not automatically roll back the transaction that moved the message from `incomingOrders` to `readyOrders`.

## 6. How scope changes with channel type

Consider two structures:

~~~text
A. Source JDBC queue
       → transactional poller
       → DirectChannel
       → handler writing JDBC on the same DataSource
~~~

~~~text
B. Source JDBC queue
       → transactional poller
       → destination JDBC queue
       → another consumer processes it
~~~

In structure A, if the handler writes JDBC synchronously and joins the current transaction, an error from the handler can roll back both the receive operation and the business update.

In structure B, the first transaction protects moving the message between the two queues. The downstream consumer needs its own transaction and error policy.

| Destination forwarded to | Work that can complete in current call | Scope to examine next |
| --- | --- | --- |
| `DirectChannel` with synchronous handler | Handler returns result or throws error | Resources and propagation inside handler |
| JDBC-backed `QueueChannel` on same DataSource | Inserts message into queue within transaction | Transaction of the destination queue's consumer |
| In-memory-only `QueueChannel` | Adds element to memory | No JDBC rollback for that element |
| `ExecutorChannel` using async executor | Hands off task to executor | Processing outcome on another thread |
| HTTP outbound adapter | Receives response per HTTP protocol | Side effects on the HTTP system |

An `ExecutorChannel` may behave differently depending on the executor and execution policy; do not rely on a task incidentally running on the calling thread when designing transactions. When synchronous guarantees are needed, pick a structure that explicitly enforces them.

A gateway must also be analyzed this way. Merely having a gateway method in code is not enough to conclude that the call, reply, and all side effects share the same transaction.

## 7. Failures during forwarding and easily confused outcomes

### 7.1. Destination queue write fails before commit

Suppose writing to `readyOrders` hits an SQL error. If the exception escapes synchronous processing and the transaction rolls back:

- The deletion on `incomingOrders` is undone.
- New data written to `readyOrders` inside the same transaction is discarded.
- The next poll can receive the source message again.

Redelivery is a fresh execution. Do not assume in-memory counters or headers modified during the failed attempt survive rollback.

### 7.2. Error after enqueueing but before commit

This is a key scenario for verifying atomicity. Returning from enqueue does not mean the transaction has committed.

If a synchronous step after enqueue throws an error, the shared JDBC transaction can still roll back both removing from the source and adding to the destination. In the lab, you can deliberately throw an error after `ready.send(message)` to observe this state.

### 7.3. Catching the error and continuing

~~~java
try {
    forwardToDestination(message);
}
catch (RuntimeException ex) {
    logger.error("Forwarding failed", ex);
    // Returning normally: the transaction may still commit.
}
~~~

If the goal is retrying from the source, let an appropriate error escape the transaction boundary, or make an explicit rollback decision. If you choose to route failing messages to a quarantine queue and commit, that is a different business outcome and must be designed deliberately.

Do not confuse logging with a rollback decision.

### 7.4. Filters and routers can end a flow normally

A filter dropping a message without throwing an exception can allow the receive to commit, even though no message reaches the expected destination. A router sending to another branch can also complete normally.

Therefore, "not seeing it in the destination queue" does not prove the transaction rolled back. Check the configured behavior of each endpoint: drop, route to discard channel, route to another branch, or raise an error.

## 8. errorChannel, retry, and repeated failing messages

`errorChannel` serves error publishing and handling; having a message there is not a data-rollback mechanism.

In a typical synchronous poller setup, errors exit the transaction advice so the transaction is resolved, and then the polling infrastructure reports the error. If an advice or recovery handler inside the flow catches the error and returns normally before it reaches the transaction advice, the commit/rollback outcome can change.

Therefore distinguish:

1. The resource's commit or rollback decision.
2. Sending error details to a monitoring flow.
3. The message retry policy.

Do not assume audit records or messages sent by an error flow always belong to the original transaction. Determine when it runs, on which thread, and under which transaction.

Once the source is restored after rollback, the poller can continue redelivering the failing message. If the error is permanent—for instance, an unconvertible payload—infinite retries only waste resources.

A handling policy may include:

- Bounded retries for transient errors.
- Moving unprocessable messages to a quarantine queue.
- Persisting attempt counts somewhere with an appropriate lifecycle, instead of relying on changes that also roll back.
- Alerting when the same business key fails repeatedly.

Retry around a handler and retry around the whole receive–process unit have different scopes. When combining retry advice with transaction advice, advice order decides whether a retry reuses the current transaction or opens a new one. Choose the scope before adding configuration.

## 9. Is one scheduled run one transaction for multiple messages?

`maxMessagesPerPoll` bounds the number of message receive cycles within one triggered run. It does not by default turn all messages in that cycle into a single batch transaction.

With a synchronous polling endpoint and standard transaction advice, the advice wraps each execution of the receive-and-forward unit. The scheduled loop invokes that unit multiple times. You can verify how polling tasks and loops are structured in [AbstractPollingEndpoint](https://github.com/spring-projects/spring-integration/blob/main/spring-integration-core/src/main/java/org/springframework/integration/endpoint/AbstractPollingEndpoint.java).

For example, when no outer transaction wraps the loop:

~~~text
maxMessagesPerPoll = 3

Receive 1: message A → commit transaction A
Receive 2: message B → commit transaction B
Receive 3: message C → rollback transaction C
~~~

A and B are not undone just because C failed. Conversely, if a `MessageSource` returns a single message whose payload is a list, that is one receive unit containing multiple items; distinguish that from multiple receives.

The main example sets `maxMessagesPerPoll(1)` to keep observation straightforward. If a batch of messages must succeed or fail together, design explicit batching and corresponding transaction boundaries rather than merely increasing this parameter.

`receiveTimeout` is the wait time for receiving, whereas transaction timeout is the transaction limit enforced by the transaction manager. The two values serve different purposes. If a transaction is already open while waiting on the source, the wait time also affects how long the unit of work holds resources.

## 10. Verifying atomicity with practice exercises

Verification must inspect resource state after the transaction finishes. Observing that a handler ran or logs appeared is not enough.

### 10.1. Testing the store with an explicit transaction

The test snippet below uses the same JDBC configuration above. The bridge remains stopped thanks to `autoStartup(false)`, so the scheduler does not compete with the test to pull messages.

The test deliberately receives, sends successfully, and then throws an error before commit. It verifies that both queues participate in the JDBC transaction. It does not yet verify wiring the transaction advice on the poller.

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig({
        JdbcLabConfiguration.class,
        ReceiveForwardConfiguration.class
})
@DirtiesContext
class ReceiveForwardRollbackTest {

    @Autowired
    @Qualifier("incomingOrders")
    PollableChannel incoming;

    @Autowired
    @Qualifier("readyOrders")
    PollableChannel ready;

    @Autowired
    @Qualifier("receiveForwardTxManager")
    PlatformTransactionManager transactionManager;

    @Test
    void restoresSourceAndRemovesDestinationInsertOnRollback() {
        // Seed is committed before the transaction used to simulate failure.
        Message<String> original = MessageBuilder
                .withPayload("order-1042")
                .setHeader("businessKey", "order-1042")
                .build();

        assertTrue(incoming.send(original));

        TransactionTemplate transaction =
                new TransactionTemplate(transactionManager);

        assertThrows(IllegalStateException.class, () ->
                transaction.executeWithoutResult(status -> {
                    Message<?> message = incoming.receive(0);
                    assertNotNull(message);

                    assertTrue(ready.send(message));

                    // Error after forwarding but before commit.
                    throw new IllegalStateException("Simulated failure");
                }));

        assertNull(ready.receive(0));

        Message<?> restored = incoming.receive(0);
        assertNotNull(restored);
        assertEquals("order-1042", restored.getPayload());
        assertEquals(
                "order-1042",
                restored.getHeaders().get("businessKey"));

        assertNull(incoming.receive(0));
    }
}
~~~

Do not place this test inside an outer test transaction, because seed data must exist independently and we want to observe the real outcome of the transaction under test.

The `receive(0)` calls in the assertion section are destructive reads that mutate the queue. They fit this isolated fixture; do not use them as a harmless inspection technique in production environments.

### 10.2. Verifying the real poller configuration

To verify the full endpoint, add scenarios using the real scheduler and transaction advice:

| Scenario | Setup | What to observe after completion |
| --- | --- | --- |
| Normal commit | Run the bridge as in the demo | Source is empty, destination receives matching business key |
| Error at destination | Use a test destination that throws synchronously | Source message can still be received again |
| Error after enqueue | In a test flow, handler writes to destination queue then throws | Source is restored; no destination record from the failed attempt |
| In-memory source | Replace only source with `new QueueChannel()` | JDBC rollback does not restore source item |
| Async destination | Hand off to executor then trigger worker error | Worker error does not revert already-committed transaction |

When testing failure scenarios, limit run count or stop the endpoint once the failure is recorded and the transaction has completed. Letting the poller run continuously can cause a redelivery to interfere while inspecting results.

Use latches, well-placed completion signals, or condition waits with timeouts. Do not conclude a transaction has finished merely because an error callback was invoked inside a handler; that callback can run before rollback completes.

Include a business key in the payload/headers to correlate messages by business meaning. The framework's Message ID does not replace the system's deduplication key.

## 11. Boundaries transactions do not solve automatically

### 11.1. JDBC transactions and HTTP side effects

Suppose a handler makes an HTTP call to charge payment and then writes to the destination queue. If HTTP succeeds but writing to the queue fails, JDBC rollback can restore the source; it does not automatically refund the charge on the HTTP system.

When the message is redelivered, the HTTP call may repeat. In this scenario, consider idempotency keys, compensating actions, or an appropriate multi-step workflow.

### 11.2. Two independent resources

If receiving from a broker and writing to an independent database, identify a coordination mechanism supported by both resources. Design approaches may include distributed transactions when supported and warranted, or outbox/inbox combined with idempotent processing.

Enabling transactions on the poller alone does not prove two systems share a single atomic commit.

### 11.3. Sending after commit

Moving the send out to an `afterCommit` callback avoids sending before the database commits, but creates a different gap: the database has committed while the subsequent send may fail or the process may crash.

If sends must not be lost, persist the intent to send durably and provide a replay mechanism. An after-commit callback by itself does not provide that guarantee.

### 11.4. Business-level exactly-once

Local transactions can protect moving messages between the two JDBC queues in the example very well. However, that does not automatically create an exactly-once guarantee for the entire business process across consumers, remote systems, and retries.

Define which actions must not repeat per business key, then design storage and checks specifically for those actions.

## 12. Common configuration mistakes

| Symptom | What to check |
| --- | --- |
| Source loses message despite JDBC rollback | Is the source an in-memory queue, or did receive happen before the transaction? |
| Destination data still remains after failure | Does the destination use the same DataSource, transaction, and propagation? |
| Downstream error does not cause source redelivery | Is there a queue, executor, or recovery handler in between? |
| Nothing runs | Is the endpoint stopped due to `autoStartup(false)`? |
| JDBC store fails to start | Was the schema created and does the query provider match the database? |
| Failing message processed repeatedly in a loop | Do retry and quarantine policies handle permanent errors? |
| Old data missing after config change | Did the store's group ID, database, or region change? |
| Data lost after closing demo | Is an in-memory H2 database being used? |
| Flaky test results | Is the scheduler racing with `receive` calls in assertions? |

When analyzing a flow, draw the transaction boundary directly onto the operations: begin transaction, receive, invoke handler, send, commit. Then mark participating resources and every thread switch. Reading a flow this way lets you pinpoint what a failure rolls back and where processing resumes afterward.
