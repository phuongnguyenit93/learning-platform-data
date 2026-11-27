# Transactional poller

In the **Poller transaction** chapter of the **SPRING_INTEGRATION_CORE** module, a transactional poller helps define when receiving a message and processing business logic are treated as a single successful unit of work. This lesson connects Message, MessageChannel, endpoints, and Java DSL with Spring's transaction management mechanism.

The main example uses a JDBC queue containing order IDs. The poller retrieves a message, invokes the handler, and writes the result to the same database. From there, we analyze commit, rollback, error handling, reprocessing, and testing. The Java snippets use Spring Integration 6.5 APIs and Java 17; dependencies should be managed consistently using an appropriate BOM for the application.

## 1. Expected outcomes

After this lesson, you will be able to:

- Explain why a transaction must begin before the message receive operation.
- Place a poller on the right endpoint in Java DSL.
- Distinguish resources that support rollback from resources that are merely called while a transaction is open.
- Identify transaction boundaries when a flow passes through DirectChannel, QueueChannel, or ExecutorChannel.
- Verify both the queue state and business data together.

You should already know that a Message consists of payload and headers, QueueChannel requires consumers to actively receive messages, and DirectChannel invokes subscribers synchronously.

## 2. Where do pollers appear?

| Scenario | Polling component | Receive operation |
| --- | --- | --- |
| Endpoint reading from a PollableChannel, such as QueueChannel | PollingConsumer | Receive message from channel |
| Inbound adapter reading from an external source | SourcePollingChannelAdapter | Call MessageSource to create or fetch a message |

A service activator receiving data from a QueueChannel needs a poller on the service activator's endpoint. A JDBC inbound adapter needs a poller on the source-reading adapter. DirectChannel does not need a poller to dispatch messages to subscribers. See [Poller in Spring Integration](https://docs.spring.io/spring-integration/reference/polling-consumer.html).

A poller has two groups of responsibilities:

1. **Scheduling:** when to poll and the maximum number of receives per scheduled poll.
2. **Wrapping work:** applying transaction advice and other advice.

Merely configuring a one-second interval does not create atomicity for receiving and processing a message.

## 3. Why putting @Transactional only on the service may not be enough

Consider this design:

~~~text
QueueChannel
    -> receive message
    -> service with @Transactional
    -> update DB
~~~

The transaction on the service starts when the service is invoked. The message retrieval happens before that. If retrieving the message needs to be rolled back when business logic fails, starting the boundary at the service is too late.

A transactional poller wraps the polling work—including receiving the message and subsequent processing on the same call chain—in transaction advice. The source must actually participate in the transaction for the receive operation to be rolled back. See [Poller Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html).

Desired model for the example:

~~~text
Begin JDBC transaction
    -> retrieve message from JDBC queue
    -> record order in DB
    -> complete synchronous processing
Commit both changes
~~~

If the handler throws an error before commit:

~~~text
Begin JDBC transaction
    -> retrieve message from JDBC queue
    -> INSERT business data
    -> handler throws IllegalStateException
Rollback:
    - INSERT is not saved
    - message removal from the store is not confirmed
~~~

This model assumes **the same JDBC resource**. Any external systems called inside the handler do not automatically participate in that transaction.

## 4. Which resources are actually rolled back?

| Configuration | When handler fails |
| --- | --- |
| Default in-memory QueueChannel, handler writes JDBC in a transaction | JDBC writes can roll back; the already-received message is not automatically returned to the queue |
| QueueChannel using JdbcChannelMessageStore, poller and handler share the same managed DataSource | Message retrieval and DB writes can roll back together |
| File source, handler writes JDBC | JDBC writes can roll back; filesystem operations do not automatically become ACID |
| Handler sends HTTP request then a JDBC error occurs | The HTTP request already executed by the receiver is not automatically undone |

By default, QueueChannel keeps messages in memory. Persistent storage requires configuring a message store or appropriate messaging infrastructure. With a transaction-capable persistent store, removing a message from the store becomes a confirmed change only when the transaction succeeds. See [configuring a persistent QueueChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

Evaluate these separately:

- **Durability:** does the message survive after the process stops?
- **Transactional receive:** can retrieving the message be undone along with business logic?

You cannot infer both properties just by looking at the name QueueChannel. Even a store that persists data must be used with the right transaction manager and resource-access mechanism.

## 5. Thread boundaries

### 5.1. Synchronous processing flow

~~~mermaid
sequenceDiagram
    participant P as Poller thread
    participant Q as JDBC Queue
    participant H as Handler
    participant D as Business DB
    P->>D: BEGIN
    P->>Q: receive()
    Q-->>P: Message
    P->>H: synchronous processing
    H->>D: INSERT
    alt Handler succeeds
        H-->>P: completed
        P->>D: COMMIT
    else Handler throws error
        H-->>P: RuntimeException
        P->>D: ROLLBACK
    end
~~~

The JDBC Queue and Business DB in the diagram use the same DataSource; the two columns represent two roles.

DirectChannel invokes the handler on the sending thread. ExecutorChannel hands off work to an executor, so it does not guarantee preserving the transaction bound to the calling thread. QueueChannel creates a buffering point for a consumer to receive later. See [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

### 5.2. Handing off work to another thread

~~~text
Thread A:
    BEGIN T1
    receive message
    send to ExecutorChannel
    hand-off accepted
    return to poller
    COMMIT T1

Thread B:
    handler runs later
    error occurs
~~~

An error on Thread B does not automatically roll back T1, which has already committed. The commit happens when the call wrapped by transaction advice returns, not at the line declaring the channel.

This is a design consequence that must be verified whenever adding asynchronous processing. If two recoverable stages are needed, use a persistent queue between the two stages with a separate transaction for each consumer.

### 5.3. Poller TaskExecutor differs from ExecutorChannel in the flow

A poller's TaskExecutor dispatches the polling work onto a worker thread. Transaction advice is applied when that work runs. If subsequent handlers are still invoked synchronously on that same worker thread, they can still participate in the transaction.

An ExecutorChannel placed after the receive operation introduces another hand-off to a different thread. Therefore, where the transaction starts and the execution graph matter more than whether the word "executor" appears in the configuration.

The [PollerSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/PollerSpec.html) API provides separate methods—taskExecutor, transactional, receiveTimeout, and errorChannel—for these responsibilities.

## 6. Java DSL: receiving a message and writing to DB in one transaction

### 6.1. Preparation

The example requires:

- Java 17 along with compatible versions of Spring dependencies.
- spring-integration-core, spring-integration-jdbc, spring-jdbc, and the PostgreSQL JDBC driver.
- A DataSource bean named **integrationDataSource**.
- The JDBC message store schema initialized before creating and starting the related components.
- A business table in the same database accessed by integrationDataSource.

Use the schema script matching the library version and database. In the spring-integration-jdbc JAR, the PostgreSQL script is located at:

~~~text
org/springframework/integration/jdbc/schema-postgresql.sql
~~~

The script includes the INT_CHANNEL_MESSAGE table, sequence, and related indexes. Do not create only the business table and assume the message store is ready. Refer to [Spring Integration 6.5 PostgreSQL schema](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-jdbc/src/main/resources/org/springframework/integration/jdbc/schema-postgresql.sql).

Dedicated table for the illustrative business logic:

~~~sql
CREATE TABLE processed_order (
    order_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

The chosen rule is: each order_id is recorded only once. If an order has multiple event types, the deduplication key should be based on event_id or a more suitable business key.

### 6.2. Integration configuration

~~~java
import java.time.Duration;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.PostgresChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;
import org.springframework.integration.transaction.TransactionInterceptorBuilder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.interceptor.TransactionInterceptor;

@Configuration
@EnableIntegration
public class TransactionalOrderFlowConfig {

    @Bean
    public PlatformTransactionManager pollerTxManager(
            @Qualifier("integrationDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public JdbcTemplate orderJdbcTemplate(
            @Qualifier("integrationDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public JdbcChannelMessageStore orderMessageStore(
            @Qualifier("integrationDataSource") DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);
        store.setChannelMessageStoreQueryProvider(
                new PostgresChannelMessageStoreQueryProvider());
        store.setRegion("transactional-orders-v1");
        return store;
    }

    @Bean
    public QueueChannel orderQueue(
            @Qualifier("orderMessageStore") JdbcChannelMessageStore store) {
        return new QueueChannel(
                new MessageGroupQueue(store, "order-queue"));
    }

    @Bean
    public QueueChannel orderPollerErrors() {
        return new QueueChannel(100);
    }

    @Bean
    public TransactionInterceptor orderPollerTxAdvice(
            @Qualifier("pollerTxManager")
            PlatformTransactionManager transactionManager) {
        return new TransactionInterceptorBuilder()
                .transactionManager(transactionManager)
                .propagation(Propagation.REQUIRED)
                .isolation(Isolation.READ_COMMITTED)
                .timeout(10)
                .readOnly(false)
                .build();
    }

    @Bean
    public IntegrationFlow orderConsumer(
            @Qualifier("orderQueue") QueueChannel input,
            @Qualifier("orderJdbcTemplate") JdbcTemplate jdbc,
            @Qualifier("orderPollerTxAdvice")
            TransactionInterceptor transactionAdvice) {
        return IntegrationFlow.from(input)
                .handle(String.class, (orderId, headers) -> {
                    if (orderId.isBlank()) {
                        throw new IllegalArgumentException(
                                "orderId must not be blank");
                    }

                    jdbc.update("""
                            INSERT INTO processed_order(order_id)
                            VALUES (?)
                            ON CONFLICT (order_id) DO NOTHING
                            """, orderId);

                    if (Boolean.TRUE.equals(
                            headers.get("simulateFailure"))) {
                        throw new IllegalStateException(
                                "Simulated failure after INSERT");
                    }

                    return null;
                }, endpoint -> endpoint
                        .id("orderPollingEndpoint")
                        .autoStartup(false)
                        .poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                                .maxMessagesPerPoll(1)
                                .receiveTimeout(0)
                                .transactional(transactionAdvice)
                                .errorChannel("orderPollerErrors")))
                .get();
    }
}
~~~

The example does not define a DataSource because the URL, credentials, and connection pool belong to environment configuration. Make sure to provide the integrationDataSource bean before using the class above.

The endpoint has autoStartup(false) so data can be prepared and then started in a controlled manner during the lab exercise. For automatically running flows, choose a startup policy after the schema and operational configuration are ready.

### 6.3. Conditions that enable atomicity

Three components receive the same integrationDataSource:

~~~text
DataSourceTransactionManager
JdbcChannelMessageStore
JdbcTemplate
~~~

DataSourceTransactionManager manages the JDBC connection bound to the thread. JdbcTemplate uses Spring's mechanism to obtain a transaction-participating connection. Obtaining a standalone connection manually and committing it directly can fall outside this scope. See [DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html).

MessageGroupQueue connects QueueChannel to the store. The group ID "order-queue" and region "transactional-orders-v1" must remain stable across restarts to continue reading from the same queue. See [MessageGroupQueue](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupQueue.html).

The query provider must match PostgreSQL. Selecting, locking, and retrieving messages differ by database; do not use a query provider for another database. Refer to [JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html).

The handler returns null because it is a final consumption step that produces no reply. Null does not indicate failure. The simulated failure is thrown after INSERT so that rollback of modified data can be observed.

### 6.4. TransactionInterceptorBuilder

The builder creates advice with the chosen propagation, isolation, timeout, and readOnly settings. Here, the default constructor is used to create a TransactionInterceptor for the poller. The constructor with the handleMessageAdvice option serves a different advice scope; that option is not needed in this example. See [TransactionInterceptorBuilder](https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/TransactionInterceptorBuilder.html).

If only default attributes are needed, you can use transactional(transactionManager). When tighter control over attributes is required, an advice bean makes the applied configuration explicit.

### 6.5. Sending messages and starting the endpoint

The following snippet runs in code that has an ApplicationContext named context, after the schema is ready:

~~~java
import org.springframework.context.Lifecycle;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.support.MessageBuilder;

QueueChannel orders =
        context.getBean("orderQueue", QueueChannel.class);

boolean accepted = orders.send(
        MessageBuilder.withPayload("ORDER-1001")
                .setHeader("correlationId", "practice-1001")
                .build(),
        1_000);

if (!accepted) {
    throw new IllegalStateException("Cannot enqueue order");
}

Lifecycle endpoint =
        context.getBean("orderPollingEndpoint", Lifecycle.class);
endpoint.start();
~~~

Run the producer outside a transaction wrapping the entire exercise, or commit the producer transaction before starting the consumer. A successful send confirms putting the message into the queue; it does not confirm that the handler has committed.

Use a dedicated fixture for the failure branch:

~~~java
orders.send(
        MessageBuilder.withPayload("ORDER-FAIL-1002")
                .setHeader("simulateFailure", true)
                .setHeader("correlationId", "practice-failure-1002")
                .build(),
        1_000);
~~~

String payloads and String/Boolean headers fit message storage in the example. In a real application, choose payloads, headers, and serializers appropriate for the store; do not assume arbitrary runtime objects, streams, or connections can be stored.

The failing message keeps simulateFailure after rollback, so it will keep failing when redelivered. Use a separate DB/queue for the failure fixture and stop the endpoint after observing it. Subsequent polls do not automatically change this header.

### 6.6. Expected results

For the success fixture, after the transaction completes:

~~~sql
SELECT order_id
FROM processed_order
WHERE order_id = 'ORDER-1001';
~~~

The query returns one row; the corresponding message is no longer in the queue's group.

For the failure fixture, after error notification and rollback complete:

- There is no processed_order row for ORDER-FAIL-1002.
- The message can still be received again from the store.
- orderPollerErrors receives an ErrorMessage containing error details.

A log stating "INSERT executed" does not prove a commit. Verify using an independent observer connection after the transaction completes.

## 7. Is maxMessagesPerPoll the number of messages in one transaction?

In a standard synchronous poller, maxMessagesPerPoll limits the maximum number of receives within one scheduled poll. Transaction advice wraps each receive-and-process unit of work; it does not automatically wrap the entire loop in a single shared transaction.

~~~text
One scheduled poll, maxMessagesPerPoll = 3

    T1: receive A -> handle A -> commit
    T2: receive B -> handle B -> rollback due to error
    C : not processed in the poll interrupted by error
~~~

Once A has committed, it is not undone because B fails. Polling can end early when no message is available or when an exception occurs. See the polling task and loop structure in [AbstractPollingEndpoint branch 6.5](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/endpoint/AbstractPollingEndpoint.java).

Distinguish **one message** from **one record**. A JDBC inbound adapter can return a single message containing a List of multiple rows. In that case, maxMessagesPerPoll(1) can still bring multiple business rows into the same unit of work. The adapter can also run SELECT and UPDATE statements to mark rows within the poller's transaction. See [JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html).

When designing batches, determine:

1. Does one receive return a single item or a list?
2. Does a splitter process on the same thread or hand off to another thread?
3. Does a failure on a later item propagate back to the original transaction boundary?
4. Is atomicity required for the whole list or per item?

Choose maxMessagesPerPoll based on scheduling requirements after answering these points.

## 8. Choosing transaction attributes

### 8.1. Propagation

REQUIRED creates a transaction if none exists and joins an existing one if present, according to the applied manager. For a standard poller, this is a clear starting choice.

A downstream service using REQUIRES_NEW creates an independent transaction. If that service commits and a later step fails, its data does not roll back with the poller transaction. This configuration can also require an extra connection while the outer transaction holds its connection. See [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html).

In the example, do not add REQUIRES_NEW to the INSERT if the goal is for message retrieval and order recording to succeed or fail together.

### 8.2. Isolation and readOnly

The example chooses READ_COMMITTED. Increasing isolation can alter locking and contention; it does not replace the message-retrieval algorithm, query provider, or deduplication key.

A poller reading a JDBC queue may modify the store when retrieving a message. The handler also performs an INSERT, so choose readOnly(false). The words "poll" or "receive" are not enough to conclude that the work is read-only.

When scaling up consumers, measure with the actual DB, schema, provider, and expected load; do not assume every queue behaves the same way.

### 8.3. Timeout and wait times

| Parameter | Meaning in the example |
| --- | --- |
| fixedDelay(Duration.ofSeconds(1)) | Scheduling delay before the next execution |
| receiveTimeout(0) | Do not wait if the PollableChannel has no message ready |
| timeout(10) on transaction advice | Transaction timeout in seconds |
| send(message, 1_000) | Wait limit when sending to the channel, in milliseconds |

A transaction timeout is not a timer that automatically aborts arbitrary Java calls. For JDBC, enforcement depends on how the connection, statement, and driver are accessed. HTTP needs its own client timeout.

The transaction should have enough time for expected processing while avoiding holding connections and locks during slow tasks that do not need DB atomicity.

## 9. Exceptions, errorChannel, and rollback

### 9.1. Exceptions must reach the right boundary

By Spring's default, RuntimeException and Error trigger rollback; checked exceptions do not follow the same rule unless additionally configured. In messaging, handler errors may be wrapped in MessagingException, which is a runtime exception. You must examine the actual exception reaching the transaction advice. See [Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html).

The following snippet easily leads to unintended results:

~~~java
try {
    jdbc.update(
            "INSERT INTO processed_order(order_id) VALUES (?)",
            orderId);
    invokeBusinessStep();
}
catch (RuntimeException ex) {
    logger.warn("Processing failed for {}", orderId, ex);
}
~~~

If the error is swallowed, the call may finish normally and the transaction may commit. If a component has already marked rollback-only, catching the exception does not clear that flag; at commit time you may receive UnexpectedRollbackException.

When business failure must cause rollback, let an appropriate exception escape the transaction boundary, or use a clearly designed rollback-marking mechanism.

### 9.2. errorChannel forwards error information

For polling work, the framework can turn an exception into an ErrorMessage for handling via an error channel. This path supports logging, alerting, or error routing; it does not automatically provide a replay queue or prove that the source message was restored. See [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

In the example:

~~~text
Handler throws error
    -> transaction advice handles rollback
    -> polling task error handling mechanism
    -> orderPollerErrors
~~~

This is the path for handler errors before commit. Errors in afterCommit have a different meaning because the DB may already have committed.

orderPollerErrors is a bounded-capacity QueueChannel for observation. If it is not drained, the queue can fill up. Production applications need an error-consuming flow and appropriate persistence/audit logging.

### 9.3. A flow finishing normally can still commit

A filter rejecting a message without throwing an error is a normal processing decision. A router successfully directing a message to another branch does not signal rollback either.

If the requirement is to quarantine invalid messages, model a quarantine branch. If the requirement is to keep the message for retry, the transaction boundary must receive an appropriate failure signal. The two requirements yield different queue outcomes.

## 10. Rollback, retry, and reprocessing

| Concept | Role |
| --- | --- |
| Rollback | Undoes changes on resources participating in the transaction |
| Retry at handler | Re-invokes a step according to an advice policy |
| Reprocessing from source | Consumer receives again a message that was not acknowledged or was returned to the source |

RequestHandlerRetryAdvice applies retry to a handler. In typical stateless usage, it can re-invoke the handler on the same thread. If retry sits inside the poller's transaction, each attempt does not by default get a fresh JDBC transaction. See [Retry Advice in Spring Integration 6.5](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/classes.html).

A clear observation pattern for the lab:

~~~text
First receive:
    T1 -> receive message -> write DB -> error -> rollback

Next receive:
    T2 -> receive message again -> reprocess
~~~

If the JDBC transaction is no longer usable after an SQL error, retrying the handler within the same transaction may not help. Determine the retry scope, transaction state, and the effect of any recovery callback.

A recovery callback returning normally can make the outer call see the error as handled. Test the queue and DB outcomes of the exact advice chain rather than just counting handler invocations.

### Poison messages

The simulateFailure header creates a message that always fails. Transactions preserve the ability to redeliver, but they do not fix bad data or permanent business errors.

Operational design must decide:

- Which errors to retry and which to quarantine?
- Where to store attempt counts so they are not lost on restart?
- When the limit is exceeded, how are removing from the source and writing to quarantine made atomic?
- Who fixes the data and replays it?

If the retry counter lives inside the same transaction that always rolls back, the counter may also roll back. Local variables or newly added headers lost upon rollback are insufficient for a durable policy.

## 11. Idempotency when reprocessing is possible

Design must account for duplicate messages, producer resends, and side effects outside the DB.

The unique key order_id combined with ON CONFLICT DO NOTHING prevents the example from inserting an extra row when the order ID already exists. PostgreSQL provides ON CONFLICT to choose behavior upon unique constraint conflicts. See [PostgreSQL INSERT](https://www.postgresql.org/docs/current/sql-insert.html).

This choice follows the "record each order once" rule. If the same order_id appears with different content, ignoring conflicts could hide data errors. Real applications must decide whether to validate payloads, versions, or event_id.

Suppose we add an HTTP payment charge request:

~~~text
Receive message
    -> payment gateway processes successfully
    -> write DB
    -> DB error, rollback
    -> receive message again
    -> may call charge again
~~~

This is a scenario analysis for the example: a JDBC transaction is not enough to guarantee that non-DB side effects happen only once. You may need an idempotency key supported by the payment gateway or an outbox design that persists outbound requests.

Do not label the system "system-wide exactly once" merely because the poller is transactional.

## 12. Transaction synchronization and pseudo transactions

### 12.1. Callbacks based on transaction outcome

Spring provides beforeCommit, afterCommit, and afterCompletion. Errors before commit can trigger rollback; work running after commit cannot undo a completed commit. If an after-commit callback needs to write to the DB, it must define its own transaction for that operation. See [TransactionSynchronization](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html).

Spring Integration provides TransactionSynchronizationFactoryBean to configure actions based on processing outcome. For example, sending payloads to corresponding channels:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.transaction.TransactionSynchronizationFactoryBean;

@Bean
public TransactionSynchronizationFactoryBean fileCompletionSync() {
    return new TransactionSynchronizationFactoryBean()
            .afterCommit("payload", "filesCommitted")
            .afterRollback("payload", "filesRolledBack");
}
~~~

This is an additional configuration for a separate file flow, not part of the order flow. It requires two declared channels and corresponding handlers. Pass the Spring-created factory into the file flow's poller:

~~~java
Pollers.fixedDelay(Duration.ofSeconds(1))
        .transactional(fileTransactionManager)
        .transactionSynchronizationFactory(fileCompletionFactory);
~~~

fileTransactionManager and fileCompletionFactory are beans injected into that file flow configuration. See the methods and FactoryBean semantics in [TransactionSynchronizationFactoryBean API](https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/TransactionSynchronizationFactoryBean.html).

If the filesCommitted handler fails to move the file, the main transaction has already committed. Logging and reconciliation are required; callbacks do not turn a DB and filesystem into a distributed transaction.

### 12.2. PseudoTransactionManager

PseudoTransactionManager helps coordinate lifecycle-based actions for sources that lack real transactions; it does not turn a source into a transactional resource. See [PseudoTransactionManager](https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/PseudoTransactionManager.html).

~~~text
Flow completes -> post-success action
Flow fails     -> post-failure action
~~~

Do not replace DataSourceTransactionManager in the order example with PseudoTransactionManager and expect INSERT and JDBC message retrieval to still roll back. The two managers serve different purposes.

## 13. Testing transaction boundaries

Verify a pair of states together: **source message** and **business data**. Just observing that the handler was invoked does not prove commit or rollback.

Spring Integration has modules that support testing flows and components. Transaction testing still requires real resources that support the behavior being observed. See [Testing support](https://docs.spring.io/spring-integration/reference/testing.html).

### 13.1. Recommended test matrix

| Scenario | Evidence after completion |
| --- | --- |
| ORDER-1001 succeeds | One processed_order row, message leaves queue |
| Error after INSERT | No business row, message can be received again |
| Resend already-succeeded order_id | Only one business row, new message is consumed |
| Replace with in-memory queue in separate fixture | DB rolls back but message is not automatically restored |
| Insert ExecutorChannel before handler in separate fixture | Successful hand-off does not prove downstream committed |
| Restart after enqueue, before consume | Message can be read with same DB, region, and group |
| Receive A then B, B fails in same scheduled poll | A committed; B rolled back |

This is a practice plan for the learner, not a claim that the tests have already been executed.

### 13.2. Organizing fixtures

1. Initialize the schema and use a dedicated DB or data partition per scenario.
2. Keep the endpoint stopped during setup and enqueue.
3. Commit the producer before the consumer runs.
4. Start the endpoint and await the completion event with a timeout.
5. Stop the endpoint, wait for in-flight work to finish, then inspect the queue.
6. Read the DB using a fresh observer transaction/connection.
7. Clean up the fixture after gathering sufficient evidence.

Do not rely solely on Thread.sleep with a fixed duration as evidence. Use a latch tied to the completion event or wait on a condition with a timeout.

Do not wrap the entire test in @Transactional and assume the poller shares the test's transaction. If the test has not committed producer data, the consumer may not see the message yet.

Do not call orderQueue.receive() to "peek" while the poller is still running. Receive consumes the message and can alter the outcome.

### 13.3. Checking whether a transaction is active

You can temporarily add to the fixture's handler:

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();

if (!active) {
    throw new IllegalStateException(
            "Expected an active transaction in handler");
}
~~~

The active flag only proves there is a transaction on that thread. To prove the right connection/store participates, still test rollback and inspect the data.

### 13.4. Checking whether a message can be received again

After the poller stops and no work is still running, use an observer transaction and roll back the receive operation:

~~~java
import java.util.Objects;

import org.springframework.messaging.Message;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

TransactionTemplate probe = new TransactionTemplate(
        context.getBean(
                "pollerTxManager",
                PlatformTransactionManager.class));

Message<?> redelivered = probe.execute(status -> {
    Message<?> candidate = orders.receive(0);
    status.setRollbackOnly();
    return candidate;
});

if (redelivered == null
        || !Objects.equals(
                redelivered.getPayload(), "ORDER-FAIL-1002")) {
    throw new AssertionError(
            "Expected the failed order to remain available");
}
~~~

This check is for a dedicated fixture containing only the failing message to observe. The probe's rollback retains the message in the JDBC queue. It does not prove the same behavior for an in-memory queue.

## 14. Reading symptoms to find wrong boundaries

| Symptom | First check |
| --- | --- |
| DB rolls back but message disappears | In-memory queue, receive outside transaction, or wrong manager |
| Partial data remains after error | REQUIRES_NEW, auto-commit, or independently committing resource |
| Error appears on another thread | ExecutorChannel, @Async, or self-spawned thread |
| Failing message received repeatedly | No quarantine policy for permanent errors yet |
| Error logged but DB commits | Exception swallowed or error branch finishes normally |
| Test sees no consumer processing | Endpoint not started, producer not committed, or wrong group/region |
| Old message missing after restart | Changed DB, region, group ID, or not using a persistent store |
| Adding HTTP makes transaction hold locks too long | Non-DB call executed while transaction is open |

Trace messages by business key and correlationId, recording thread name, receive timestamp, handler completion timestamp, and transaction outcome. Only log payload details needed for diagnosis.

## 15. Design workflow

Write down the unit of work clearly before choosing configuration:

~~~text
Input:
    One message containing one order ID

Success:
    Message leaves JDBC queue
    Order is recorded in the same DB

Failure before commit:
    No business changes saved
    Message remains eligible for redelivery

Out of scope:
    HTTP, email, and filesystem do not automatically roll back with JDBC
~~~

Then:

1. Choose a source with appropriate receive and recovery semantics.
2. Place the transaction before receive at the poller.
3. Keep steps needing atomicity on the same thread and managed resources.
4. Explicitly choose the transaction manager when multiple managers exist.
5. Choose a deduplication key based on business semantics.
6. Define the path on error and when retry limits are exceeded.
7. Verify success, failure after DB write, and thread-boundary changes.

For the order flow in this lesson, both outcomes must be demonstrated: retrieval and DB write commit together on success, or those changes roll back together when the handler fails before commit.
