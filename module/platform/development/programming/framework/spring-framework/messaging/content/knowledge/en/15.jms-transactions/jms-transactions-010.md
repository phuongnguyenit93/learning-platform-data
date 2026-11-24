# Limits of Local Transactions When Updating Both Broker and Database

## Objectives

A business operation may need to update the database and send a message to a JMS broker. For example, when creating an order, the application both saves the order and publishes an `OrderCreated` event. When receiving an event, the consumer may both update the database and acknowledge that the message has been processed.

The problem is that the database and the JMS broker are two independent resources. A local transaction only guarantees commit or rollback for the resource that the transaction manager manages. Using one local transaction for the database and one local transaction for JMS does not create a single shared atomic transaction.

After this lesson, you can:

- Distinguish a local JMS transaction, a local database transaction, and a global transaction.
- Understand the scope of `JmsTransactionManager`, `DataSourceTransactionManager`, and `JtaTransactionManager`.
- Identify the failure windows when writing to the database and publishing messages.
- Handle redelivery when the database has committed but the JMS transaction has not committed.
- Apply transactional outbox, inbox/deduplication, and idempotency.
- Determine when XA/JTA is needed and its operational costs.

## 1. Which Resources Does a Transaction Protect?

Spring provides a common abstraction, `PlatformTransactionManager`, but each transaction manager is typically tied to one specific kind of resource.

| Transaction manager | Managed resource | Scope |
|---|---|---|
| `JmsTransactionManager` | One JMS `ConnectionFactory` | Local JMS transaction |
| `DataSourceTransactionManager` | One JDBC `DataSource` | Local database transaction |
| `JdbcTransactionManager` | One JDBC `DataSource` | Local database transaction, with integrated JDBC error handling |
| `JpaTransactionManager` | One JPA `EntityManagerFactory` | Local JPA transaction |
| `JtaTransactionManager` | XA resources enlisted in a JTA coordinator | Global/distributed transaction |

`JmsTransactionManager` manages one JMS `ConnectionFactory`. It binds the JMS Connection/Session pair to the current thread so that operations through `JmsTemplate` can participate in that same local JMS transaction.

`DataSourceTransactionManager` manages one JDBC DataSource. Operations through `JdbcTemplate` or a compatible JDBC access mechanism participate in the corresponding DataSource's transaction.

Two independent transaction managers do not automatically enlist each other's resources. If a method uses `@Transactional("dbTransactionManager")`, the selected transaction is the database transaction. That does not turn the JMS send operation into an atomic part of the database transaction.

## 2. JmsTransactionManager and Local JMS Transactions

Spring provides `JmsTransactionManager` to manage a local transaction for one JMS `ConnectionFactory`.

Example bean declaration:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.JmsTransactionManager;

@Configuration
public class JmsTransactionConfiguration {

    @Bean("jmsTransactionManager")
    JmsTransactionManager jmsTransactionManager(
            ConnectionFactory connectionFactory) {
        return new JmsTransactionManager(connectionFactory);
    }
}
~~~

When `JmsTemplate` runs inside a transaction managed by `JmsTransactionManager`, the template automatically detects the JMS Connection/Session bound to the thread and uses that resource.

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EventPublisher {

    private final JmsTemplate jmsTemplate;

    public EventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.events", event);
    }
}
~~~

This is a service fragment requiring a configured `JmsTemplate`, a JMS provider, and the `jmsTransactionManager` bean. When the method completes normally, the JMS transaction commits; if the transaction rolls back, the send operation in that transaction also rolls back according to the provider's semantics.

This scope includes only the JMS resources managed by `JmsTransactionManager`. A JDBC statement executed in the same method does not automatically belong to the JMS transaction.

## 3. Local Database Transactions

The database has its own transaction manager. For example, using JDBC:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

@Configuration
public class DatabaseTransactionConfiguration {

    @Bean("dbTransactionManager")
    DataSourceTransactionManager dbTransactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

A service that updates the database:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void updateOrder(Order order) {
        orderRepository.save(order);
    }
}
~~~

The database operations participate in `dbTransactionManager`'s transaction. If the method throws an unchecked exception and the transaction rolls back, the database changes in that transaction are rolled back.

When the application has multiple transaction managers, explicitly specify the appropriate manager on `@Transactional` or deliberately configure a default manager. Merely using one `@Transactional` annotation does not mean Spring automatically coordinates every resource injected into the service.

## 4. Why Do Two Local Transactions Not Form One Atomic Transaction?

Suppose a business operation needs to perform two operations:

1. Save changes to the database.
2. Send an event to the broker.

Each system has its own commit state. If the application commits one side and then fails before the other side commits, the two systems can fall out of sync.

~~~text
Application
   |                         |
   v                         v
Database transaction     JMS transaction
   |                         |
   v                         v
DB commit/rollback        Broker commit/rollback

The two transactions have independent outcomes if there is no shared coordinator.
~~~

Even when both operations lie in the same Java method, the transaction boundary is still decided by the transaction manager. The call order of functions does not create an atomic commit between two systems.

## 5. Failure Windows When Publishing an Event After Updating the Database

There are two common orderings, and each has its own failure window.

### 5.1. Sending JMS Before the Database Commits

For example, a method running inside a database transaction:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void createOrder(Order order) {
    orderRepository.save(order);
    jmsTemplate.convertAndSend("orders.events", toEvent(order));
}
~~~

If the JMS send operation is accepted by the broker but the database commit fails afterwards, the consumer may receive an event for a database change that rolled back.

Sequence:

~~~text
1. DB writes the order in an uncommitted transaction
2. JMS broker receives OrderCreated
3. DB commit fails
4. DB rolls back
5. Consumer may still process OrderCreated
~~~

An event that has already left for the broker is not automatically retracted when the database rolls back.

### 5.2. Sending JMS After the Database Commits

The application can register an after-commit callback or use `@TransactionalEventListener(phase = AFTER_COMMIT)` so that it publishes only when the database transaction has committed.

This avoids publishing an event when the database rolls back, but still has a gap:

~~~text
1. DB commit succeeds
2. Process stops or broker fails
3. JMS send has not completed
4. DB already has the data but the event has not been published
~~~

An `AFTER_COMMIT` callback is not a durable queue. If the process dies after the DB commit but before publishing, the event can be lost. An in-memory retry mechanism also cannot solve this crash window.

## 6. Failure Windows When Receiving a Message and Updating the Database

When a listener receives a message, Spring can use a local JMS transaction by enabling `sessionTransacted` on the listener container.

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Each listener invocation runs in a JMS transaction. If the listener throws an exception, the message receive is rolled back and the broker can redeliver the message. Sending a reply through the same JMS Session with `SessionAwareMessageListener` also belongs to that JMS transaction.

Database operations inside the listener still use a separate database transaction.

An important scenario:

~~~text
1. JMS broker delivers the message to the listener in a JMS transaction
2. Listener updates the database
3. Database commit succeeds
4. JMS commit/acknowledgement fails
5. Broker redelivers the message
6. Listener receives the message again and risks updating the database a second time
~~~

This is why Spring recommends detecting duplicate messages in the listener logic when the database has committed but the JMS transaction has not committed.

If you use an acknowledgement mode that does not guarantee rollback when the listener fails, the message may be acknowledged before the database finishes. For reliability requirements, configure a transacted session and let exceptions that need a retry propagate to the container; do not swallow exceptions after the database rolls back.

## 7. Summary Table of Failure Scenarios

| Flow | Failure point | Possible outcome | How to protect |
|---|---|---|---|
| Outbound: send then DB commit | DB rolls back after the broker received the event | Event exists while the DB change does not exist | Outbox |
| Outbound: DB commit then send | Broker fails or process stops before send | DB has changed while the event was not emitted | Outbox |
| Inbound: DB commit then JMS commit | JMS commit fails after DB commit | Message redelivery, business operation may run repeatedly | Inbox/deduplication and idempotency |
| Inbound: JMS ack before DB commit | DB rolls back after the message was acked | Message may be lost from the processing flow | JMS transacted session or XA |
| Inbound: both local txs | Process dies between the two commits | One resource may commit while the other has not committed | Inbox or XA |
| Publish retry after timeout | Broker already received the message while the producer does not know the outcome | Message may be sent in duplicate | Stable event ID and idempotent consumer |

## 8. Outbound Solution: Transactional Outbox

The transactional outbox solves the dual-write when a database update needs to emit an event.

Instead of writing to the database and then sending JMS directly in the same flow, the application writes the business change and an outbox record in **the same database transaction**.

~~~text
Business service
      |
      v
One DB transaction
   |              |
   v              v
Business table   Outbox table
   |              |
   +------ commit-+
                  |
                  v
          Outbox relay / poller
                  |
                  v
              JMS broker
                  |
                  v
              Consumers
~~~

If the database transaction rolls back, both the business row and the outbox row roll back. If the commit succeeds, the event remains durably in the outbox until the relay publishes it.

Service example:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional(transactionManager = "dbTransactionManager")
    public void createOrder(CreateOrder command) {
        Order order = Order.create(command);
        orders.save(order);

        String eventId = UUID.randomUUID().toString();
        OrderCreated event = new OrderCreated(
            eventId,
            order.id(),
            Instant.now()
        );

        outbox.insertPending(eventId, "OrderCreated", event);
    }
}
~~~

This is a service fragment; `Order`, `CreateOrder`, `OrderCreated`, `OrderRepository`, and `OutboxRepository` are application types. What matters is that both write commands use the same database transaction.

The relay reads committed outbox records, sends the payload to JMS, and then marks the record as published:

~~~java
public void publishPendingEvents() {
    for (OutboxRecord event : outbox.claimBatch()) {
        jmsTemplate.convertAndSend("orders.events", event.payload());
        outbox.markPublished(event.id());
    }
}
~~~

This is pseudocode describing the relay flow. In an actual implementation, `claimBatch()` needs a lease/locking mechanism so multiple relays do not compete for the same record; `markPublished()` needs to update the status after the broker confirms the send according to the provider's contract.

If the broker has already received the event but the process stops before `markPublished`, the relay will send the event again when it keeps running. Therefore an outbox typically provides at-least-once publishing; the consumer still needs idempotency.

Do not mark a record published before sending. If the process stops after marking it but before sending, the event will be lost from the outbox queue while the broker has not received it.

### 8.1. Fields That Should Be in the Outbox

An outbox table typically has:

| Field | Purpose |
|---|---|
| `event_id` | Stable, unique ID for the event |
| `aggregate_id` | ID of the entity or aggregate that produced the event |
| `event_type` | Event type |
| `payload` | Serialized event content |
| `created_at` | Time the event was created |
| `status` | Pending, claimed, published, or equivalent status |
| `attempt_count` | Number of times the relay attempted to send |
| `next_attempt_at` | Time when a retry is allowed |
| `published_at` | Time when publishing succeeded |

If you need to preserve event ordering for an aggregate, store a sequence/version and design the relay to emit in order within the scope of the aggregate. Ordering across multiple aggregates usually does not need to be guaranteed globally.

## 9. Inbound Solution: Inbox and Deduplication

For incoming messages, the consumer can store the ID of a processed message in an inbox table in the same transaction as the business update.

The inbox table typically has a unique constraint on `event_id`. The inbox write operation must be atomic so that two concurrent processing passes of the same event do not both get past the duplicate check.

~~~text
JMS listener receives event
        |
        v
DB transaction
   |                 |
   v                 v
Insert event_id     Update business data
   |                 |
   +------- commit --+
        |
        v
Listener method returns
        |
        v
JMS local transaction commits
~~~

Listener example:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class OrderEventListener {

    private final InboxRepository inbox;
    private final OrderProjection orders;

    public OrderEventListener(
            InboxRepository inbox,
            OrderProjection orders) {
        this.inbox = inbox;
        this.orders = orders;
    }

    @JmsListener(destination = "orders.events")
    @Transactional(transactionManager = "dbTransactionManager")
    public void handle(OrderCreated event) {
        boolean firstDelivery = inbox.tryInsert(event.eventId());

        if (!firstDelivery) {
            return;
        }

        orders.apply(event);
    }
}
~~~

This is a listener fragment requiring a repository and a database transaction manager. `tryInsert` must rely on a unique constraint or an atomic insert-if-absent statement; checking `exists` and then inserting separately can hit a race condition.

Combine the listener with a factory that enables `sessionTransacted=true`. When the DB transaction commits but the JMS commit fails, the broker can redeliver. On the redelivery, the inbox detects that `event_id` already exists and does not apply the business logic again.

If the DB transaction fails, the exception needs to propagate out so that the transaction rolls back and the JMS container rolls back the message receive. For checked exceptions, configure `rollbackFor` or convert to an unchecked exception when appropriate under the error-handling policy.

The inbox protects changes inside the same DB transaction. If the listener also calls an HTTP API, sends an email, or creates side effects in another system, those side effects need idempotency or a separate outbox.

### 9.1. Choosing a Stable Message ID

You can use an application event ID in the payload or in a JMS property. Use an ID generated by the producer and kept unchanged across retries.

Do not rely by default only on `JMSMessageID` if a producer retry can create a new message with a different JMSMessageID for the same business operation. A stable event ID helps the consumer recognize the same event across multiple sends.

There needs to be a policy for retaining and cleaning up inbox records. Do not delete an ID before the window in which messages may be redelivered or replayed expires.

## 10. XA/JTA: One Global Transaction for Multiple Resources

When business requirements mandate that the database update and the JMS receive/send must commit or roll back together, you can use XA with JTA.

The JTA transaction coordinator coordinates the XA resources participating in the transaction, for example:

- An XA-capable JMS ConnectionFactory.
- An XA-capable JDBC DataSource.
- Spring's `JtaTransactionManager` connecting to the transaction coordinator.

High-level two-phase commit flow:

~~~text
Application
    |
    v
JTA transaction coordinator
    |
    +---- XA resource: Database
    |
    +---- XA resource: JMS broker

Phase 1: PREPARE
    Coordinator asks each resource whether it can commit.
    Resources write the prepared state to the transaction log.

Phase 2: COMMIT or ROLLBACK
    Coordinator decides the overall outcome and sends the command to the resources.
~~~

High-level Spring configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.jta.JtaTransactionManager;

@Configuration
public class GlobalTransactionConfiguration {

    @Bean
    JtaTransactionManager transactionManager() {
        return new JtaTransactionManager();
    }
}
~~~

Example of a listener container participating in a JTA-managed transaction:

~~~java
@Bean
DefaultJmsListenerContainerFactory xaListenerFactory(
        ConnectionFactory xaConnectionFactory,
        JtaTransactionManager transactionManager) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(xaConnectionFactory);
    factory.setTransactionManager(transactionManager);
    return factory;
}
~~~

With `JmsTemplate`, use `JtaTransactionManager` together with an XA-capable `ConnectionFactory`. The database must also use an XA DataSource and be registered with the same transaction coordinator. Inside a `@Transactional` method using the JTA manager, the enlisted resources can participate in the global transaction.

**XA does not work automatically merely by declaring `JtaTransactionManager`.** You must configure the broker, JDBC driver, XA ConnectionFactory, XA DataSource, transaction coordinator, and recovery log properly. If a resource only supports local transactions, that resource does not automatically become an XA participant.

### 10.1. Pros and Cons of XA

| Aspect | Characteristics |
|---|---|
| Atomicity | Enlisted XA resources are coordinated to commit/roll back together |
| Consistency | Shrinks the state-divergence window between the database and the broker |
| Cost | Adds prepare/commit round trips, transaction logs, and recovery |
| Resource locking | Resources may hold a prepared state while waiting for the decision |
| Operations | Requires monitoring the transaction coordinator and handling in-doubt transactions |
| Compatibility | Broker, driver, and datasource must support XA and be configured properly |

Spring also recommends considering a local JMS transaction plus duplicate detection when duplicates can be tolerated in some process failures. That approach is usually lighter than XA. Choose XA when atomicity across resources is truly necessary and the infrastructure can operate distributed transactions.

## 11. Can AFTER_COMMIT Replace an Outbox?

Spring provides `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` and transaction synchronization callbacks to run code after the database transaction commits.

Example:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void publishAfterCommit(OrderCreated event) {
    jmsTemplate.convertAndSend("orders.events", event);
}
~~~

This approach ensures the callback only runs after the originating transaction commits successfully. It is useful for best-effort side effects or when the system accepts that manual handling may be required if publishing fails.

However, the callback does not persist the event durably. If the process stops after the database commit but before the callback or during the send, there is no outbox record for a relay to retry after startup. Therefore AFTER_COMMIT does not provide the same level of guarantee as a transactional outbox.

If you use the callback, clearly define how to retry, record errors, and recover unpublished events. For important events, an outbox is usually easier to control.

## 12. Sagas and Business Processes Spanning Multiple Services

XA can coordinate XA resources under one transaction coordinator. But a business workflow may span multiple services, each owning its own database and broker, or calling external HTTP APIs. Those systems usually do not participate together in one XA transaction.

A Saga splits a long process into multiple local transactions. Each step commits in the service that owns the data; if a later step fails, the system runs a compensating action to bring the business state back to an acceptable state.

Order-placement example:

1. Order Service creates the order in `PENDING` status and emits `OrderCreated`.
2. Payment Service attempts to collect payment and emits `PaymentSucceeded` or `PaymentFailed`.
3. If payment succeeds, Order Service transitions the order to `CONFIRMED`.
4. If payment fails, Order Service cancels the order or transitions it to `CANCELLED`; if inventory was reserved, Inventory Service executes a reservation release.

A Saga provides eventual consistency and business-level compensation. It is not a global database/JMS transaction and compensating actions can also fail, so retry, idempotency, and tracking state are needed.

## 13. Choosing a Solution by Requirement

| Requirement | Appropriate solution |
|---|---|
| Only need a transaction for JMS send operations | `JmsTransactionManager` or a transacted JMS Session |
| Only need a transaction for DB updates | `DataSourceTransactionManager`, `JdbcTransactionManager`, or `JpaTransactionManager` |
| DB updates must always have durable outbound events | Transactional outbox |
| Listener updates the DB and may receive the same message again | Transacted JMS session + inbox/deduplication |
| DB and JMS receipt/send must be atomic in one transaction | JTA/XA with all resources XA-capable |
| Business workflow spans multiple services | Saga with local transactions and compensating actions |
| Non-critical side effect, best-effort acceptable | AFTER_COMMIT callback with appropriate logging/retry |

No single choice fits every system. Determine what must be atomic, whether duplicates are acceptable, whether the broker/provider supports XA, and whether the operations team can manage a transaction coordinator.

## 14. Common Mistakes

- **Assuming one `@Transactional` automatically includes both DB and JMS:** the annotation uses one specific transaction manager. Other resources are not automatically enlisted.
- **Using `JmsTransactionManager` to roll back JDBC:** this manager only manages one JMS ConnectionFactory.
- **Using `DataSourceTransactionManager` to roll back a JMS send:** a database transaction does not control the broker's commit.
- **Enabling `sessionTransacted=true` and assuming the DB also rolls back:** the flag only creates a local JMS transaction for the listener invocation.
- **Sending an event inside a DB transaction and assuming the send rolls back with the DB:** the two resources commit separately if XA is not used.
- **Using AFTER_COMMIT like an outbox:** the callback does not persist events durably when the process crashes.
- **Not handling duplicates after redelivery:** the DB may have committed while the JMS commit failed.
- **Using `exists` then inserting into the inbox in two separate operations:** two concurrent consumers can both pass the check; a unique constraint and atomic insert are needed.
- **Swallowing exceptions in the listener:** the container may commit the JMS transaction even though business processing failed.
- **Using XA with non-XA resources:** the transaction manager cannot guarantee atomicity for a resource that cannot be enlisted.
- **Marking the outbox published before the broker receives the message:** a crash in between can lose the event.
- **Assuming an outbox guarantees exactly-once:** the relay may send duplicates if the broker receives the message while the published status has not yet been saved.

## 15. Design Checklist

- [ ] Identified the transaction manager managing each resource.
- [ ] Distinguished the local JMS transaction from the local DB transaction.
- [ ] Identified the commit order and the failure windows for both outbound and inbound.
- [ ] Considered a transactional outbox for important outbound events.
- [ ] Outbox row and business update use the same DB transaction.
- [ ] Relay sends first and marks published afterwards, with retry and a lease/locking mechanism.
- [ ] Events have a stable ID and consumers process idempotently.
- [ ] For inbound listeners, enabled a transacted JMS session when reliability is needed.
- [ ] Inbox insert and business update use the same DB transaction.
- [ ] Inbox has a unique constraint or an atomic insert operation.
- [ ] Exceptions requiring rollback propagate to the listener container.
- [ ] If using XA, both the JMS ConnectionFactory and the DataSource are XA-capable and enlisted.
- [ ] Configured the transaction coordinator, timeouts, logs, and recovery.
- [ ] Considered a Saga when the workflow spans multiple services.
- [ ] Tested broker outage, DB outage, process crash between the two commits, redelivery, and duplicate events.

## 16. References

- [Spring Framework — Using Spring JMS: Transaction Management](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — Receiving a Message: Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework — JmsTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [Spring Framework — JtaTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/jta/JtaTransactionManager.html)
- [Spring Framework — DataSourceTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Boot — Distributed Transactions With JTA](https://docs.spring.io/spring-boot/reference/io/jta.html)
- [AWS Prescriptive Guidance — Transactional Outbox Pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
