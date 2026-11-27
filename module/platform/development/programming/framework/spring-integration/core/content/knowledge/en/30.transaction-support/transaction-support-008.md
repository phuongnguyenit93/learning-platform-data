# Transactions with MessageStore

In Spring Integration Core, a flow typically passes through `Message`, `MessageChannel`, and processing endpoints. When a channel or endpoint must retain messages for later processing, that state becomes part of business correctness. This lesson belongs to the **Transaction support** chapter and focuses on coordinating MessageStore with transactions so receiving, storing, and processing messages produce consistent outcomes.

The running scenario is order intake: the application inserts an order into the database, places a processing request onto a JDBC-backed channel, and lets a poller process it later. The goal is to avoid two states: having an order without a processing request, or having the request vanish while the order has not yet been processed successfully.

After this lesson, you should be able to explain:

- Which store suits a queue, and which store suits an aggregator.
- Where a transaction starts in order to cover the `receive()` operation.
- Why producer and consumer have two independent transactions.
- Rollback limits when a flow switches threads or calls external systems.
- How to verify rollback, restarts, and duplicate handling using a real database.

## 1. Durability and transactions solve two different problems

**Durability** answers the question: does a successfully saved message survive a process restart?

**Atomicity** answers the question: do operations on the message and business changes commit or roll back together?

A queue stored in a database can still lose a business processing opportunity if the application retrieves the message in one transaction that commits, and then processes business logic in another transaction that rolls back. Conversely, putting a transaction around an in-memory queue does not make memory contents durable after the JVM stops.

| Design approach | After process stop | When handler fails |
| --- | --- | --- |
| Default in-memory `QueueChannel` | Pending messages may be lost | No JDBC rollback mechanism to restore the retrieved message |
| JDBC-backed queue, received outside poller transaction | Committed messages in queue can be recovered | Retrieval may have already completed before business failure |
| JDBC-backed queue, received and processed in the right shared transaction | Committed messages stay in database | Message deletion and business updates can roll back together |
| Transactional JDBC queue, but handler calls HTTP | Database still has a transaction | HTTP already executed on another system is not automatically undone |

Channel documentation confirms an important mechanism: with a transactional persistent store, message removal only becomes permanent when the transaction wrapping the poller commits successfully. [MessageChannel configuration reference](https://docs.spring.io/spring-integration/reference/6.5/channel/configuration.html).

From this, the required contract for the order example is:

```text
Intake TX:
    INSERT order
    INSERT message into JDBC queue
    COMMIT both or ROLLBACK both

Processing TX:
    RECEIVE message from JDBC queue
    UPDATE order
    COMMIT both or ROLLBACK both
```

These two blocks execute at different times. Atomicity is guaranteed within each block when resources and transactions are configured properly.

## 2. Choosing the right MessageStore type

The name "MessageStore" is often used generally for where messages are saved. In actual configuration, inspect the interface and the implementation's purpose.

| Component | Responsibility | Usage example |
| --- | --- | --- |
| `MessageStore` | Store and retrieve individual messages | Claim check: hold message, pass reference key |
| `MessageGroupStore` | Manage message groups and group state | Aggregator, resequencer |
| `ChannelMessageStore` | Contract for storing and retrieving channel messages | Externalized queue storage |
| `JdbcMessageStore` | General-purpose JDBC store supporting messages and groups | Aggregator, claim check |
| `JdbcChannelMessageStore` | JDBC store specialized for channels | JDBC-backed `QueueChannel` |
| `SimpleMessageStore` | In-memory store | Testing or non-durable state |

`JdbcMessageStore` suits group state; `JdbcChannelMessageStore` is designed for channels and is not a substitute for an aggregator's store. [JDBC Message Store reference](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html), [JdbcMessageStore API](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/store/JdbcMessageStore.html).

In the main example:

```text
orderInbox (QueueChannel)
    └── MessageGroupQueue
          └── JdbcChannelMessageStore
                └── PostgreSQL
```

`MessageGroupQueue` bridges the queue API with the store. When reusing a queue after a restart, preserve the queue's group identifier. If a new `UUID` is generated for `groupId` on every startup, the application may see an empty queue while old messages remain in the database. [MessageGroupQueue API reference](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupQueue.html).

## 3. Producer and consumer transaction boundaries

The following diagram shows one intake and one failed processing attempt.

```mermaid
sequenceDiagram
    participant Client as Caller
    participant Producer as Intake service
    participant DB as Database
    participant Poller as Poller
    participant Handler as Business handler

    Client->>Producer: submit(orderId)
    Producer->>DB: BEGIN TX-P
    Producer->>DB: INSERT app_order
    Producer->>DB: INSERT message into queue
    Producer->>DB: COMMIT TX-P
    Producer-->>Client: Accepted

    Poller->>DB: BEGIN TX-C1
    Poller->>DB: RECEIVE message
    Poller->>Handler: handle(orderId)
    Handler->>DB: UPDATE app_order
    Handler--xPoller: RuntimeException
    Poller->>DB: ROLLBACK TX-C1
    Note over DB: Message stays for redelivery; UPDATE is undone

    Poller->>DB: BEGIN TX-C2
    Poller->>DB: RECEIVE message again
    Poller->>Handler: handle(orderId)
    Handler->>DB: UPDATE app_order
    Handler-->>Poller: Complete
    Poller->>DB: COMMIT TX-C2
```

The client receiving "Accepted" only means the producer's transaction finished. It does not confirm that the consumer has finished processing.

When a flow is triggered by a poller, the transaction must be established around the polling operation so it includes `receive()`. Putting `@Transactional` solely on the handler only starts a transaction at the handler invocation; that may be too late to protect removing the message from the queue. [Poller Transaction Support reference](https://docs.spring.io/spring-integration/reference/6.5/transactions.html).

## 4. Java DSL example: JDBC queue and business data sharing a resource

### 4.1. Example prerequisites

The example uses Spring Integration 6.5 APIs, Java 17, and PostgreSQL. When applying it to a project, use compatible Spring versions managed by your project's BOM or Spring Boot.

Required:

- `spring-integration-core` to define channels, endpoints, and Java DSL.
- `spring-integration-jdbc` to use JDBC MessageStore.
- `spring-jdbc` and `spring-tx`; may already be brought in transitively.
- PostgreSQL JDBC driver and a `DataSource` bean.
- When running tests: JUnit Jupiter, `spring-test`, and `spring-integration-test`.

Assume a single `DataSource` in the example's application context. The database holds both the business table and the store tables. `JdbcTemplate`, the store, and `DataSourceTransactionManager` all use this exact `DataSource` bean.

Pointing to the same database URL is not enough if code creates its own connections outside the transaction. `DataSourceTransactionManager` manages thread-bound connections for a `DataSource`; `JdbcTemplate` coordinates with that mechanism. [DataSourceTransactionManager reference](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html).

### 4.2. Preparing the schema before starting the flow

Create the Spring Integration tables using the PostgreSQL script bundled with the exact version of `spring-integration-jdbc` in use. For this reference line, the resource is located at:

```text
org/springframework/integration/jdbc/schema-postgresql.sql
```

This script contains the `INT_CHANNEL_MESSAGE` table, associated sequences, and tables for the general store. Do not strip the schema down to just a payload column; the store also needs identifiers, region, and ordering metadata. [View PostgreSQL schema in Spring Integration 6.5 source](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-jdbc/src/main/resources/org/springframework/integration/jdbc/schema-postgresql.sql).

Also create the business table:

```sql
CREATE TABLE app_order (
    order_id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(16) NOT NULL,
    CONSTRAINT app_order_state_ck
        CHECK (state IN ('NEW', 'PROCESSED'))
);
```

Apply the schema via migrations before the context starts. Do not re-run `CREATE TABLE` every time the poller receives a message. In production environments, migrations must also preserve pending messages across application upgrades.

### 4.3. Complete flow and service configuration

Save the following class in your application's package and import or component-scan it. The `DataSource` bean is supplied by the runtime environment as described above.

The payload is a `String` containing the order ID. Choosing this payload keeps the example focused on transactions; do not put JPA entities or channel objects into durable storage.

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel
        .PostgresChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

@Configuration
@EnableIntegration
@EnableTransactionManagement
public class OrderIntegrationConfig {

    @Bean("integrationTxManager")
    public PlatformTransactionManager integrationTxManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public JdbcChannelMessageStore channelMessageStore(
            DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);
        store.setChannelMessageStoreQueryProvider(
                new PostgresChannelMessageStoreQueryProvider());
        store.setRegion("orders-v1");
        return store;
    }

    @Bean
    public QueueChannel orderInbox(
            JdbcChannelMessageStore channelMessageStore) {
        return new QueueChannel(
                new MessageGroupQueue(
                        channelMessageStore, "order-inbox"));
    }

    @Bean
    public OrderSubmissionService orderSubmissionService(
            JdbcTemplate jdbcTemplate,
            @Qualifier("orderInbox") QueueChannel orderInbox) {
        return new OrderSubmissionService(jdbcTemplate, orderInbox);
    }

    @Bean
    public OrderHandler orderHandler(JdbcTemplate jdbcTemplate) {
        return new OrderHandler(jdbcTemplate);
    }

    @Bean
    public IntegrationFlow consumeOrders(
            @Qualifier("orderInbox") QueueChannel orderInbox,
            OrderHandler orderHandler,
            @Qualifier("integrationTxManager")
                    PlatformTransactionManager txManager) {

        return IntegrationFlow.from(orderInbox)
                .handle(orderHandler, "handle",
                        endpoint -> endpoint
                                .id("orderConsumer")
                                .poller(Pollers.fixedDelay(500)
                                        .maxMessagesPerPoll(1)
                                        .transactional(txManager)))
                .get();
    }

    public static class OrderSubmissionService {

        private final JdbcTemplate jdbc;
        private final QueueChannel inbox;

        public OrderSubmissionService(
                JdbcTemplate jdbc, QueueChannel inbox) {
            this.jdbc = jdbc;
            this.inbox = inbox;
        }

        @Transactional(transactionManager = "integrationTxManager")
        public void submit(String orderId) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException(
                        "orderId must not be blank");
            }

            jdbc.update(
                    "INSERT INTO app_order(order_id, state) "
                            + "VALUES (?, 'NEW')",
                    orderId);

            boolean accepted = inbox.send(
                    MessageBuilder.withPayload(orderId)
                            .setHeader("eventType", "OrderAccepted")
                            .build());

            if (!accepted) {
                throw new IllegalStateException(
                        "Failed to enqueue request into orderInbox");
            }
        }
    }

    public static class OrderHandler {

        private final JdbcTemplate jdbc;

        public OrderHandler(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public void handle(String orderId) {
            int changed = jdbc.update(
                    "UPDATE app_order SET state = 'PROCESSED' "
                            + "WHERE order_id = ? AND state = 'NEW'",
                    orderId);

            if (changed == 0) {
                Integer alreadyProcessed = jdbc.queryForObject(
                        "SELECT COUNT(*) FROM app_order "
                                + "WHERE order_id = ? "
                                + "AND state = 'PROCESSED'",
                        Integer.class, orderId);

                if (alreadyProcessed == null
                        || alreadyProcessed != 1) {
                    throw new IllegalStateException(
                            "Invalid order: " + orderId);
                }
            }
        }
    }
}
```

A transaction manager is explicitly passed to `Pollers.transactional(...)`. This avoids relying on the application happening to have a bean named `transactionManager`. The poller API supports configuring transaction advice around the polling task. [PollerSpec reference](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/PollerSpec.html).

Calling the Spring-managed service:

```java
// Bean injected from the application context.
orderSubmissionService.submit("ORD-2026-001");
```

Do not instantiate `new OrderSubmissionService(...)` manually and expect annotations to work. With standard proxying, external calls must pass through the bean proxy; self-invocation also does not start a new transaction automatically.

### 4.4. Interpreting the example's behavior

On the producer side, `INSERT app_order` and storing the message run inside `submit()`'s transaction. If storing the message fails or `send()` returns `false`, the exception causes the transaction to fail. The order is not permitted to commit alone.

On the consumer side, the poller opens a transaction before receiving the message. The handler updates the order inside that same transaction because it uses `JdbcTemplate` and the same `DataSource` on the processing thread. When the handler finishes normally, the transaction commits and the message is no longer in the queue.

The handler permits duplicate processing requests for an order already in `PROCESSED` state. This only protects the state transition in the example database. It does not turn intake via `submit()` into an idempotent API: calling `submit()` again with the same order ID will hit the primary key constraint and must be handled according to a dedicated API contract.

`maxMessagesPerPoll(1)` helps observe each message individually while learning and testing. This parameter limits the number of messages per poll; do not treat it as a guarantee that all messages in an arbitrary poll belong to a single batch transaction.

Do not mark the consumer's transaction as `readOnly`: receiving from the JDBC queue mutates storage state, and the handler also executes an `UPDATE`.

## 5. How do gateways, channels, and endpoints affect transactions?

A messaging gateway lets business code send requests via an interface instead of calling `MessageChannel.send()` directly. It does not automatically turn the entire asynchronous processing pipeline into a single transaction.

Example interface replacing direct sends:

```java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "orderInbox")
public interface OrderIngress {
    void accept(String orderId);
}
```

If using this variant, register the gateway via `@IntegrationComponentScan` on the appropriate package, inject `OrderIngress` into the intake service, and call `accept(orderId)` right inside the producer transaction. This is an alternative send mechanism; do not both call the gateway and keep `inbox.send(...)`, as that would create two requests.

A gateway method returning `void` fits receiving now and processing later. Do not expect a temporary request `replyChannel` to remain a usable address after an application restart.

Draw boundaries according to actual channel behavior:

| Path | Where can the current transaction continue? |
| --- | --- |
| Handler calls forward through `DirectChannel` on same thread | Operations participating in the right resource can stay in the current transaction |
| Sending to a JDBC queue | Storing the message can join the sending transaction; consumer receives later in another transaction |
| Sending through `ExecutorChannel` | The downstream thread does not automatically inherit the sender thread's JDBC transaction |
| Handler calls `@Async` or spawns a thread | Work on the new thread requires its own transaction boundary |
| Calling HTTP from handler | A database transaction does not cover commits in a remote HTTP system |

When introducing an asynchronous segment, determine whether the handoff point is durably persisted or lives only in memory. If the poller successfully hands off to an in-memory executor, the poller's transaction can commit before processing on the executor fails.

Spring Integration models imperative transactions per thread; channel boundaries that switch threads must be designed as handoffs between transactions. [Transaction Boundaries reference](https://docs.spring.io/spring-integration/reference/transactions.html#transaction-boundaries).

## 6. Propagation and multiple resources

### 6.1. `REQUIRED` usually fits synchronous processing inside a poller

When the poller already has a transaction, a business service using `REQUIRED` with the corresponding transaction manager can join that transaction. Receiving the message and updating business data therefore remain in the same commit unit.

### 6.2. `REQUIRES_NEW` creates independent outcomes

Suppose the handler invokes a service with `REQUIRES_NEW`:

```text
Outer TX:
    RECEIVE message
    Inner TX (REQUIRES_NEW):
        UPDATE order
        COMMIT
    Subsequent processing fails
    ROLLBACK outer TX
```

The message can return to the queue, yet the inner transaction's changes have already committed. If the business logic credits balances, deducts inventory, or inserts new records, redelivery can create duplicate side effects.

`REQUIRES_NEW` also needs an independent connection while the outer transaction holds its resource; consider connection pool capacity. [Transaction Propagation reference](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html).

### 6.3. Two databases or two transaction managers do not merge into one transaction

If the store uses database A and business data uses database B, a `DataSourceTransactionManager` managing only A will not automatically roll back B.

Design options include:

- Consolidating state that must commit atomically onto the same resource if requirements allow.
- Using a distributed transaction mechanism when all resources and infrastructure provide appropriate support.
- Using an outbox and idempotent consumers to coordinate across multiple commits.

With JPA, select the transaction manager and JDBC coordination according to actual resources. Do not add a second JDBC transaction manager and assume it will automatically synchronize atomically with an existing JPA transaction.

## 7. Transactions with aggregators and MessageGroupStore

An aggregator must hold multiple messages until the release condition is satisfied. There are two distinct state layers:

1. Messages waiting in the input channel.
2. Messages plus metadata already placed inside the aggregator's group.

If the input channel uses JDBC but the aggregator's groups live only in memory, stopping the JVM after messages have been received can still lose incomplete groups.

Use `JdbcMessageStore` for groups. The configuration snippet below is a standalone extension of the example, added to a `@Configuration` class; it still uses `DataSource`, `channelMessageStore`, and `integrationTxManager` from above.

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.integration.store.MessageGroupQueue;
import org.springframework.transaction.PlatformTransactionManager;

// @Bean methods reside in the application's @Configuration class.

@Bean
public JdbcMessageStore shipmentGroupStore(DataSource dataSource) {
    JdbcMessageStore store = new JdbcMessageStore(dataSource);
    store.setRegion("shipment-groups-v1");
    return store;
}

@Bean
public QueueChannel shipmentInbox(JdbcChannelMessageStore store) {
    return new QueueChannel(
            new MessageGroupQueue(store, "shipment-inbox"));
}

@Bean
public QueueChannel shipmentResults(JdbcChannelMessageStore store) {
    return new QueueChannel(
            new MessageGroupQueue(store, "shipment-results"));
}

@Bean
public IntegrationFlow aggregateShipments(
        @Qualifier("shipmentInbox") QueueChannel inbox,
        @Qualifier("shipmentResults") QueueChannel results,
        JdbcMessageStore shipmentGroupStore,
        @Qualifier("integrationTxManager")
                PlatformTransactionManager txManager) {

    return IntegrationFlow.from(inbox)
            .aggregate(aggregator -> aggregator
                            .messageStore(shipmentGroupStore)
                            .expireGroupsUponCompletion(false),
                    endpoint -> endpoint
                            .id("shipmentAggregator")
                            .poller(Pollers.fixedDelay(500)
                                    .maxMessagesPerPoll(1)
                                    .transactional(txManager)))
            .channel(results)
            .get();
}
```

The flow uses default correlation and release strategies. Inputs must carry matching `CORRELATION_ID`, `SEQUENCE_NUMBER`, and `SEQUENCE_SIZE` headers, such as from a splitter with sequencing. Do not send two arbitrary messages and expect them to form a group automatically.

Suppose group `SHIP-42` has two parts:

```text
Receiving part 1:
    receive from shipmentInbox
    add part 1 to group SHIP-42
    incomplete → commit group state

Receiving part 2:
    receive from shipmentInbox
    add part 2 to group SHIP-42
    complete → produce result and store into shipmentResults
    update group state
    commit
```

In a single-thread, shared-resource configuration, an error when storing the result can roll back changes from receiving part 2. Part 1, committed earlier, remains persisted; the current transaction does not rewind the history of every message in the group.

Retaining completed groups with `expireGroupsUponCompletion(false)` helps handle late-arriving messages according to group state. You will need a metadata cleanup policy later. If multiple nodes update groups concurrently, use an appropriate shared `LockRegistry`; an in-memory lock in one JVM does not synchronize other JVMs. Timeouts or reapers running in separate tasks also need their own transaction boundaries if expiration actions must be atomic. [Aggregator reference](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html).

## 8. Exceptions, errorChannel, retries, and poison messages

### 8.1. Exceptions must reach the right transaction boundary

Under Spring's default rollback configuration, `RuntimeException` and `Error` trigger rollback; checked exceptions require explicit rules if rollback is desired. When passing through endpoints, exceptions may be wrapped into messaging exceptions; check the exception type reaching the transaction advice. [Rollback rules reference](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html).

A common mistake:

```java
public void handle(String orderId) {
    try {
        updateOrder(orderId);
    }
    catch (RuntimeException ex) {
        logFailure(orderId, ex);
        // Returning normally: transaction advice may see success.
    }
}
```

If the transaction has not been marked rollback-only, catching the error and returning can cause commit and remove the message from the queue. If the error should trigger redelivery, let the exception reach the transaction advice or explicitly mark rollback per the processing contract.

### 8.2. Error notifications do not replace rollback

`errorChannel` serves to carry error information as an `ErrorMessage`. For scheduled poller errors, the error-handling mechanism can publish a notification after the exception has exited the section protected by transaction advice.

Therefore, distinguish:

- Recovery inside the transaction scope that caught the exception and returned success.
- An error handler merely recording that a poll iteration rolled back.
- An error handler starting a new transaction of its own to persist operational data.

Seeing a log entry on `errorChannel` is not enough to prove whether the message committed or rolled back. Inspect queue state and business data. [Error Handling reference](https://docs.spring.io/spring-integration/reference/error-handling.html).

### 8.3. Rollback-and-redeliver vs. handler retry have different scopes

Rolling back the entire receive allows the message to be picked up again in a new transaction. Retry advice on a handler may simply re-invoke the handler inside the existing transaction, depending on advice ordering.

If the transaction has already been marked rollback-only or the database has put the transaction into an aborted state, retrying SQL inside that same transaction will not create a clean session. Determine whether retry wraps the entire transaction boundary or just a single handler call. [Retry Advice reference](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html#retry-advice).

For permanently failing messages, infinite rollback can cause the message to be redelivered endlessly and block subsequent messages. Designs need attempt limits, backoff delays, and a destination to quarantine unprocessable messages.

An intentional handoff pattern is:

```text
Final processing TX:
    RECEIVE message from main queue
    save failure details to quarantine queue in same database
    COMMIT
```

The quarantine queue must be durable and participate in the same transaction if moving between queues is to be atomic. If writing to the quarantine queue fails, let the transaction roll back. Do not send to an in-memory channel and treat that as proof the failed message was safely preserved.

Attempt counters also need dedicated design: incrementing a counter inside the same transaction that rolls back loses that increment. An in-memory counter is lost on restart. Do not assume `JdbcMessageStore` automatically supplies a complete dead-letter policy.

### 8.4. Filters and routers can end processing validly

A filter discarding a message without throwing an exception can cause the transaction to commit. A router producing no output under an allowed configuration can also end the flow without further business work.

If business rules state "invalid messages must be kept for inspection," configure a durable discard channel or appropriate handling branch. If the rule is "this error must trigger redelivery," emit a failure signal reaching the transaction boundary. Do not infer rollback merely because a flow produces no output.

## 9. Why are idempotency and outbox still necessary?

Suppose a consumer receives a message, successfully calls a payment API, and then loses connectivity before the database transaction commits. The database may roll back the receive, causing the message to reappear. The next processing run may call the payment API a second time.

A `MessageStore` transaction cannot recall a payment transaction already accepted by another system. A stable business identifier, such as `paymentRequestId`, must be used as an idempotency key on the side susceptible to duplicate effects.

In the order example, `NEW → PROCESSED` is idempotent for a single order ID. If replaced with `balance = balance - amount`, a duplicate execution has a different effect; you need business keys, unique constraints, or a processed-events table updated in the same transaction.

An outbox separates persisting intent from calling external systems:

```text
Database TX:
    receive message
    update business data
    INSERT outbox(event_id, payload)
    commit

Publisher:
    read outbox
    send to external system
    record sent status
```

The publisher can still resend after a crash between "sent" and "recorded sent." Therefore, an outbox must pair with an idempotency contract on the receiving side. Do not call this a system-wide exactly-once guarantee merely because the queue resides in a database.

`afterCommit` callbacks also do not eliminate the failure window: the process can stop after commit but before the callback or before sending finishes. `PseudoTransactionManager` only coordinates success/failure callbacks; it does not perform resource commit/rollback like a real JDBC transaction manager. [Transaction Synchronization and Pseudo Transactions reference](https://docs.spring.io/spring-integration/reference/transactions.html#pseudo-transactions).

## 10. Serialization, identifiers, and recovery after restart

Stored messages must still be readable later. Treat payloads and headers as a durable data contract.

For the example:

- A `String` payload and `String` `eventType` header do not depend on entities attached to a persistence context.
- `region = orders-v1` and `groupId = order-inbox` must remain stable across restarts for the same queue.
- Data from another environment must not accidentally share the same namespace.
- Changes to payload classes or serializers must account for pending older messages.

With stores using default Java serialization, payloads and persisted entries must satisfy the implementation's serialization requirements. Do not rely on non-serializable headers always being preserved; channel objects, streams, connections, or bean references are not reliable durable contracts. Some versions also restrict deserializable classes; application DTOs must be configured according to the framework version's API. [Message Store and serialization notes reference](https://docs.spring.io/spring-integration/reference/message-store.html).

If a result must be returned after a long delay or across a restart, persist a business correlation ID and publish the result to a stable address. A temporary reply channel created for a synchronous call is not a post-restart reply recovery mechanism.

When deploying a new version, retain the ability to read backlog messages or provide an explicit migration step. Changing `region` or `groupId` to "clean the queue" simply makes the application look at a different partition; unprocessed older messages still need to be managed.

## 11. Verification with a real database

A mock store is suitable for verifying method invocations. It does not prove that message retrieval and business SQL share a transaction.

With the PostgreSQL query provider, test against PostgreSQL. Do not use H2 and assume all SQL behavior and locking on PostgreSQL are equivalent.

### 11.1. Scenarios to observe

| Case | How to create the scenario | State to verify |
| --- | --- | --- |
| Producer commit | Call `submit()`, keep consumer stopped | `NEW` order and one message are persisted |
| Producer rollback | Insert order, send message, then cause an error in the same transaction | Neither the order nor the attempt's message is committed |
| Consumer commit | Receive and update order successfully | `PROCESSED` order, message gone |
| Consumer rollback | Cause error after `UPDATE` but before commit | Order remains `NEW`, same message can be received again |
| Restart | Persist message then create a new application context with the same database and identifiers | New context receives the old message |
| Duplicate processing request | Resend request for an already processed order | No extra business side effect created |
| Wrong thread boundary | Hand off to executor then cause error on the new thread | Test detects what committed before the error |
| Incomplete aggregator | Persist one part, restart, then send remaining part | Group resumes rather than losing persisted part |

Use `@SpringIntegrationTest(noAutoStartup = "orderConsumer")` to keep the endpoint stopped in tests that need direct control over the queue. This name matches `.id("orderConsumer")` in the configuration. [Spring Integration Test Context reference](https://docs.spring.io/spring-integration/reference/6.5/testing.html).

### 11.2. Illustrating a test where receive and business update roll back together

Place the following test snippet inside a test class that loads `OrderIntegrationConfig`, provides a PostgreSQL `DataSource` with schema initialized, and uses the annotation above to keep the consumer stopped.

Additional imports: `Autowired`, `Test`, `Message`, `UUID`, `TransactionTemplate`, and JUnit Jupiter static assertions. `QueueChannel`, `JdbcTemplate`, `PlatformTransactionManager`, and `Qualifier` are used as in the earlier configuration.

```java
@Autowired
private OrderIntegrationConfig.OrderSubmissionService submissionService;

@Autowired
private OrderIntegrationConfig.OrderHandler orderHandler;

@Autowired
@Qualifier("orderInbox")
private QueueChannel orderInbox;

@Autowired
private JdbcTemplate jdbcTemplate;

@Autowired
@Qualifier("integrationTxManager")
private PlatformTransactionManager txManager;

@Test
void receiveAndBusinessUpdateRollBackTogether() {
    // Do not wrap this test in an outer @Transactional transaction.
    // Test queue and database must be isolated from other tests.
    String orderId = "ORD-" + UUID.randomUUID();
    TransactionTemplate tx = new TransactionTemplate(txManager);

    // Producer transaction commits before consumer transaction starts.
    submissionService.submit(orderId);

    Message<?>[] firstAttempt = new Message<?>[1];

    try {
        assertThrows(IllegalStateException.class, () ->
                tx.executeWithoutResult(status -> {
                    Message<?> message = orderInbox.receive(0);
                    assertNotNull(message);
                    assertEquals(orderId, message.getPayload());
                    firstAttempt[0] = message;

                    orderHandler.handle((String) message.getPayload());

                    // Throw error after UPDATE to observe both parts rolling back.
                    throw new IllegalStateException("Simulated error");
                }));

        assertEquals("NEW", jdbcTemplate.queryForObject(
                "SELECT state FROM app_order WHERE order_id = ?",
                String.class, orderId));

        tx.executeWithoutResult(status -> {
            Message<?> redelivered = orderInbox.receive(0);
            assertNotNull(redelivered);
            assertEquals(orderId, redelivered.getPayload());
            assertEquals(firstAttempt[0].getHeaders().getId(),
                    redelivered.getHeaders().getId());

            orderHandler.handle((String) redelivered.getPayload());
        });

        assertEquals("PROCESSED", jdbcTemplate.queryForObject(
                "SELECT state FROM app_order WHERE order_id = ?",
                String.class, orderId));

        // No more messages. The observation call is also inside a transaction.
        tx.executeWithoutResult(status ->
                assertNull(orderInbox.receive(0)));
    }
    finally {
        jdbcTemplate.update(
                "DELETE FROM app_order WHERE order_id = ?", orderId);
        // The test fixture is responsible for cleaning up the store in the test database
        // if an assertion fails before successful consumption.
    }
}
```

This test verifies resource characteristics and transaction scope when calling `receive()` directly. It does not yet confirm that the production poller has the proper advice attached.

Add another test that starts the real `orderConsumer` endpoint: produce a message, trigger a controlled handler error, observe rollback, and then let the next attempt succeed. When running asynchronously, wait on a bounded condition rather than using a fixed `sleep` and hoping the poller ran.

Restart tests must close the old context, keep the same database, and create a new context. Merely calling `stop()` and `start()` on the endpoint inside the same context does not prove recovery after losing all process memory.

## 12. Diagnosing common incidents

| Symptom | What to inspect |
| --- | --- |
| Handler fails yet message does not return | Does the poller have a transaction wrapping `receive()`? Is recovery catching errors inside? |
| Business SQL rolls back yet queue still loses message | Do the store and business code truly use the same resource, connection, and transaction scope? |
| Message returns yet business data changed | Is there `REQUIRES_NEW`, another transaction manager, or an out-of-transaction update? |
| Restart sees empty queue though database still has rows | Did `region`, `groupId`, schema, or table prefix change? |
| Service called without transaction | Was it called via bean proxy? Was `new` or self-invocation used? |
| Cannot read old messages | Serializer, payload class, data version, and deserialization restrictions |
| Multiple nodes produce wrong aggregator results | Shared store without shared `LockRegistry` or duplicate correlation IDs? |
| One failing message keeps being received | Are retry limits, backoff, durable counters, and a quarantine queue in place? |
| Throughput drops when adding threads | Inspect row locks, long transactions, query plans, and connection pool |

For competing consumers, evaluate database and query provider locking behavior. If `usingIdCache` is needed, configure cache cleanup callbacks for both commit and rollback per documentation; an in-JVM cache does not replace cross-node coordination. Do not enable a concurrency option simply because it appeared in an example for a different database. [JdbcChannelMessageStore API reference](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/store/JdbcChannelMessageStore.html).

Useful operational metrics include pending message count, oldest message age, rollback count, redelivery count per business ID, processing duration, lock wait time, and quarantined message count. A steadily growing queue can be caused by slow consumers, transactions holding locks too long, or a failing message blocking processing; looking at queue depth alone does not distinguish those causes.

When reviewing a design, explicitly identify three things: **which state is durably persisted, which operations share a transaction, and which effects can be duplicated**. With MessageStore, the answers must come from the store, transaction manager, channels, and the actual path of the message.
