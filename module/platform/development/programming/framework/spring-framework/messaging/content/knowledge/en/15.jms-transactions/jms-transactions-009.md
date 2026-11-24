# JTA, XA, and Coordinating JMS with the Database

An application often needs to do two things in the same business operation: update data in the database and send a JMS message. For example, when creating an order, the application writes the order to the database and then publishes an OrderCreated event for other services to process.

If the two operations use two independent local transactions, an inconsistent state can occur: the database has committed but the message was not sent, or the message was sent but the database rolled back. **JTA and XA** provide a mechanism to coordinate multiple resources in one global transaction so that a unified decision to commit or roll back is made.

In Spring, **JtaTransactionManager** connects Spring's transaction model with JTA. When both the JMS provider and the database support XA and are properly registered with the same transaction manager, the application can bring JMS send/receive operations and database operations into a shared transaction.

## 1. The Dual-Write Problem Between JMS and the Database

Suppose the order-creation service performs:

~~~text
1. INSERT the order into the database
2. Send OrderCreated to the JMS queue
~~~

If the database and JMS use separate transactions, there are two failure windows:

| Order | Incident | Possible state |
|---|---|---|
| Database commits first, JMS send afterwards | The broker loses its connection after the database commits | The order exists but there is no event. |
| JMS send first, database commit afterwards | The database rolls back after the broker has accepted the message | The consumer receives an event for an order that was not saved. |

A local transaction only protects the resources belonging to that transaction. For example:

- A JDBC transaction protects operations on one database connection.
- A JMS Session transaction protects the send/receive operations in that Session.
- Two separate transactions do not automatically become one atomic transaction just because they are in the same Java method.

If the application needs the database and JMS to succeed together or fail together, it must use an appropriate coordination mechanism. XA/JTA is one option; a transactional outbox is another option when XA cannot or should not be deployed.

## 2. What Are JTA and XA?

The two concepts are related but have different responsibilities.

### JTA: The API and Transaction Coordination Model

**Jakarta Transactions (JTA)** defines a standard API for applications and transaction managers to work with global transactions. The important components include:

- **UserTransaction:** an API to begin, commit, or roll back a transaction in models that let the application control transaction boundaries.
- **TransactionManager:** the component that manages the transaction context, enlists resources, and coordinates the transaction.
- **Transaction:** represents a transaction context; resources can be enlisted into this context.

In Spring, **org.springframework.transaction.jta.JtaTransactionManager** is an implementation of Spring's PlatformTransactionManager that delegates coordination to the application server's JTA transaction manager or to a configured transaction coordinator.

JTA gives the application a unified way of working with the transaction manager. JTA does not by itself turn an ordinary JMS ConnectionFactory or DataSource into an XA resource.

### XA: The Coordination Contract Between the Transaction Manager and the Resource Manager

**XA** is a protocol/contract for a transaction manager to coordinate multiple resource managers in one global transaction. A resource participating in XA provides an **XAResource** object so that the transaction manager can:

- Attach the resource to the transaction with start.
- End the work on the resource with end.
- Ask the resource to prepare to commit with prepare.
- Order a commit or rollback.
- Recover a transaction left unfinished after a failure.

In the JMS and database problem:

| Component | Role in the global transaction |
|---|---|
| JTA transaction manager | Creates the global transaction, enlists resources, and coordinates commit/rollback. |
| JMS provider XA | Enlists message send or receive through the provider's XA resource. |
| Database XA | Enlists JDBC changes through the XADataSource/XA resource. |
| Spring JtaTransactionManager | Connects Spring's transaction annotations and API with the JTA manager. |

**JTA is the API/coordination layer; XA is the contract for resources participating in a distributed transaction.** To get a JMS + database transaction, both resources must support XA and be registered with the same transaction manager.

## 3. How Does Two-Phase Commit (2PC) Work?

XA typically uses the two-phase commit protocol to coordinate multiple resource managers.

~~~text
Application
   |
   | begin global transaction
   v
JTA Transaction Manager
   |
   +------ enlist ------> JMS XA Resource
   |
   +------ enlist ------> Database XA Resource
   |
   | Phase 1: PREPARE
   |----------------------------->
   | ask each resource whether it can commit?
   |
   | Phase 2: COMMIT or ROLLBACK
   |----------------------------->
   v
Transaction completed
~~~

### Phase 1: Prepare

1. The transaction manager begins the global transaction and creates a transaction identifier.
2. The application performs the database and JMS operations. Each resource is enlisted into the transaction.
3. When the application requests a commit, the transaction manager asks each XA resource to prepare.
4. Each resource writes the necessary state to a durable log and replies with a result:
   - **XA_OK:** the resource has prepared and can commit when asked.
   - **XA_RDONLY:** the resource has no changes to commit; it does not need to take part in the next commit phase.
   - A rollback result or an error indicates the transaction cannot commit as intended.

### Phase 2: Commit or Rollback

- If all resources with changes agree to prepare, the transaction manager writes the commit decision into the transaction log and then asks the resources to commit.
- If a resource refuses or the transaction is marked rollback, the transaction manager asks the resources to roll back.
- After completion, the transaction manager releases the transaction state.

The important point is that a resource that has replied to prepare may keep the transaction state in an in-doubt form and wait for the final decision. Therefore, the transaction manager must store a log durable enough to recover the decision after the process or server fails.

### When the Transaction Manager or Broker Fails

If the server stops after prepare but before every resource receives the commit order, the transaction may be in an in-doubt state. When the system restarts:

1. The transaction manager reads the stored transaction log.
2. It performs a recovery scan with the registered XA resources.
3. The resources return the Xids that still need handling.
4. The transaction manager reconciles with the log and continues to commit or roll back according to the recorded decision.

Do not delete the transaction log while transactions that need recovery still exist. You need to configure recovery credentials, stable resource identifiers, and the ability to reconnect to the correct JMS provider/database.

### Heuristic Outcome

In severe failure situations, a resource manager may make a heuristic decision on its own, for example committing or rolling back contrary to the decision the transaction manager intended. A mixed result can then appear: one resource has committed while another has rolled back.

XA reduces the risk of inconsistency through coordination and recovery, but does not eliminate the need to monitor in-doubt transactions, heuristic errors, and the recovery log.

## 4. Conditions for JMS and the Database to Participate in XA

Configuring JtaTransactionManager alone is not enough. Each resource must be provided in XA form and managed by the transaction coordinator.

### JMS Resource

The JMS provider must provide XA support. Under Jakarta Messaging, the related APIs include XAConnectionFactory, XAConnection, and XASession; the provider uses an XAResource to take part in the global transaction.

In a Jakarta EE environment, the application usually obtains a **JTA-aware, XA-capable ConnectionFactory** that the application server has configured and registered via JNDI. Do not create an ordinary client ConnectionFactory yourself and assume it can enlist in JTA.

### Database Resource

The database driver/provider must support XA, usually via an **XADataSource**. The application server or an XA connection pool creates a transaction-managed DataSource for the application to use via JDBC.

Do not create connections directly from an XADataSource in each business method and call the XAResource yourself. The transaction manager and the resource integration are responsible for enlisting, preparing, committing, rolling back, and recovering.

### Transaction Manager and Recovery

The transaction coordinator must support XA and be configured with both the JMS resource and the database resource. Check:

- Is the JMS ConnectionFactory registered as an XA resource?
- Is the DataSource truly an XA/JTA-managed DataSource?
- Do both resources participate in the same JTA transaction manager?
- Where is the transaction log durably stored?
- Can recovery reconnect with the broker and the database after a restart?
- Are the timeouts of the transaction, the broker, and the database compatible?

A DataSource or ConnectionFactory that merely carries the name "XA" in the configuration is not enough; you need to confirm the actual integration and test rollback/commit across failures.

## 5. Distinguishing Local Transaction, JmsTransactionManager, and JTA/XA

Spring has several transaction managers, each protecting a different scope of resources.

| Mechanism | Scope | Does it coordinate JMS and the database atomically? |
|---|---|---|
| JMS Session transacted | The JMS operations in one Session | Does not automatically coordinate the database. |
| **JmsTransactionManager** | One JMS ConnectionFactory | No. |
| **DataSourceTransactionManager** | One JDBC DataSource | Does not automatically coordinate JMS. |
| **JpaTransactionManager** | One EntityManagerFactory/database within its supported scope | Does not automatically coordinate JMS. |
| **JtaTransactionManager + XA resources** | Multiple XA resource managers in one global transaction | Yes, if all resources are enlisted correctly. |

For example, if a method calls JmsTemplate and JdbcTemplate but Spring only uses DataSourceTransactionManager, that transaction does not automatically include the JMS send. If you use JmsTransactionManager, the database is also not automatically brought into the same transaction.

Combining two local transaction managers by call order does not create a two-phase commit. When one side commits successfully and the other fails, there is still an inconsistency window.

Spring's JmsTemplate can participate in a JTA transaction when using a JTA transaction manager with a JMS ConnectionFactory configured for XA correctly. JmsTransactionManager suits a local JMS transaction when you only need to protect one ConnectionFactory.

## 6. Using JtaTransactionManager with JmsTemplate and JdbcTemplate

In Spring, the business code can still use the familiar abstractions:

- **@Transactional** marks the transaction boundary.
- **JdbcTemplate** performs database operations.
- **JmsTemplate** sends JMS messages.
- **JtaTransactionManager** coordinates the global transaction.

When both JdbcTemplate and JmsTemplate use resources managed for XA by the same transaction manager, the two operations can participate in the same global transaction.

### Resource Configuration

The configuration example below assumes the application server has provided:

- Bean **xaDataSource**: a DataSource managed by JTA and backed by an XADataSource.
- Bean **xaJmsConnectionFactory**: a JMS ConnectionFactory with XA support that is registered with the JTA transaction coordinator.

The bean names are only reference names in the example. How JNDI is declared and how the pool is configured depends on the application server or the JMS/database provider.

~~~java
@Configuration
@EnableJms
@EnableTransactionManagement
public class XaMessagingConfiguration {

    @Bean
    public JtaTransactionManager jtaTransactionManager() {
        // In Jakarta EE, Spring automatically detects the container's JTA transaction manager.
        return new JtaTransactionManager();
    }

    @Bean
    public JdbcTemplate jdbcTemplate(
            @Qualifier("xaDataSource") DataSource dataSource
    ) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public JmsTemplate jmsTemplate(
            @Qualifier("xaJmsConnectionFactory")
            ConnectionFactory connectionFactory
    ) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    public DefaultJmsListenerContainerFactory jtaJmsListenerContainerFactory(
            @Qualifier("xaJmsConnectionFactory")
            ConnectionFactory connectionFactory,
            JtaTransactionManager jtaTransactionManager
    ) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setTransactionManager(jtaTransactionManager);

        return factory;
    }
}
~~~

In this configuration:

- JtaTransactionManager is the shared transaction manager.
- JdbcTemplate uses a DataSource that is managed by JTA.
- JmsTemplate uses an XA/JTA-aware ConnectionFactory.
- The listener container uses the same JtaTransactionManager to bring both the message receive operation and the listener processing into the transaction.

**Do not set sessionTransacted=true as a local transaction in place of JTA.** When using an external transaction manager, configure transactionManager on DefaultJmsListenerContainerFactory and let JTA coordinate the transaction.

In Jakarta EE, JtaTransactionManager by default can detect the container's transaction infrastructure. For a standalone application, you need to install and configure a suitable JTA provider, for example an embedded transaction manager that supports XA and recovery. Spring does not supply an XA transaction coordinator merely by adding an annotation.

## 7. Producer Example: Writing to the Database and Sending JMS in the Same Transaction

Suppose a service creates an order. It needs to insert a record and publish an event. If any operation fails before the commit, both resources must roll back.

~~~java
package com.example.messaging;

import java.math.BigDecimal;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPublisher {

    private final JdbcTemplate jdbcTemplate;
    private final JmsTemplate jmsTemplate;

    public OrderPublisher(
            JdbcTemplate jdbcTemplate,
            JmsTemplate jmsTemplate
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "jtaTransactionManager")
    public void createOrder(String orderId, BigDecimal total) {
        jdbcTemplate.update(
                "insert into orders(order_id, total, status) values (?, ?, ?)",
                orderId,
                total,
                "CREATED"
        );

        // The String is converted into a TextMessage by Spring JMS SimpleMessageConverter.
        jmsTemplate.convertAndSend(
                "orders.created",
                "OrderCreated:" + orderId
        );
    }
}
~~~

If the database insert succeeds but the JMS send fails, the exception causes the transaction to roll back; the database insert is not committed. If the JMS send has been accepted by the resource but the database operation fails afterwards, the global transaction's rollback decision also applies to the JMS resource.

When the method ends normally, Spring asks JTA to commit the global transaction. The transaction manager coordinates the XA resources according to its commit procedure.

The code is the integration part of the business logic. To actually run it, you need the orders table, an XA DataSource, an XA JMS ConnectionFactory, a JTA transaction manager, and the orders.created destination to be configured.

## 8. Consumer Example: Receiving JMS and Updating the Database in the Same Transaction

For a message listener, you need to bring **both the message receive operation and the listener execution** into the shared transaction. If you only place @Transactional on a service called from the listener but the listener container does not participate in JTA, the JMS acknowledge/consume may still lie outside the database transaction.

Spring's **DefaultMessageListenerContainer** supports an external transaction manager. When configured with JtaTransactionManager and an XA-aware ConnectionFactory, the message receive and the database operation in the listener can belong to the same global transaction.

~~~java
package com.example.messaging;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final JdbcTemplate jdbcTemplate;

    public OrderCreatedListener(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @JmsListener(
            destination = "orders.created",
            containerFactory = "jtaJmsListenerContainerFactory"
    )
    public void handle(String body) {
        String prefix = "OrderCreated:";

        if (body == null || !body.startsWith(prefix)) {
            throw new IllegalArgumentException("Invalid order event");
        }

        String orderId = body.substring(prefix.length());

        int updated = jdbcTemplate.update(
                "update orders set status = ? where order_id = ?",
                "PROCESSED",
                orderId
        );

        if (updated != 1) {
            throw new IllegalStateException(
                    "Expected one order row for " + orderId
            );
        }
    }
}
~~~

When the listener completes normally, the transaction manager commits the database update and the JMS receive in the same global transaction. If the listener throws an exception, the transaction rolls back; the database update is undone and the message receive is rolled back according to the provider's semantics. The broker may redeliver the message according to the redelivery policy.

You do not need to call acknowledge or commit the Session yourself in this listener. The listener container and the JTA transaction manager coordinate the delivery lifecycle.

### Why Configure the Transaction Manager on the Listener Container?

A listener can be invoked within a database transaction created by an annotation, but the operation of fetching the message from the broker has already happened before that transaction. If you want atomicity between consume and the database update, the container must open the transaction before receiving the message and keep the transaction throughout the listener execution.

With Spring, **DefaultMessageListenerContainer** supports an external transaction manager. **SimpleMessageListenerContainer** does not support this same external-transaction mechanism. Choose the correct container factory and use an XA/JTA-aware ConnectionFactory.

## 9. What Is Protected and What Lies Outside XA?

JTA/XA only coordinates resources that are truly enlisted in the global transaction.

| Operation | Is it in the XA transaction? |
|---|---|
| A JDBC update through an enlisted XA DataSource | Yes. |
| A JMS send through an enlisted XA ConnectionFactory | Yes. |
| A JMS receive through a listener container participating in JTA | Yes. |
| Writing a file directly to the filesystem | Not automatically. |
| Calling an HTTP API or sending an email | Not automatically. |
| Writing to Redis or a cache that does not support XA | Not automatically. |
| Calling a database through a connection that is not enlisted | No. |

For example, if a transaction updates the database and sends JMS and then also calls an HTTP API, JTA cannot roll back the HTTP effect that has already happened. Do not keep an XA transaction open while waiting for slow network services or services that do not support XA.

If there are side effects outside XA, you need to design appropriate idempotency, compensation, or a workflow/Saga.

## 10. Timeout, Recovery, and XA Operations

XA helps coordinate transactions but increases operational requirements. A distributed transaction can hold database locks and message state longer than a local transaction.

### Configuring Timeouts

You need to set reasonable timeouts for:

- The JTA transaction manager.
- The JDBC/database transaction and the lock timeout.
- The JMS provider/broker timeout.
- The connection pool and the wait time to obtain a resource.

A transaction timeout that is too short can cause valid work to be rolled back. A timeout that is too long can hold locks, hold messages, and consume connections for a long time.

Avoid calling HTTP, waiting for users, processing large files, or doing unbounded work inside an XA transaction.

### Recovery Log

The transaction manager needs to store a durable log to know which transactions have prepared and what the final decision is. Operations must ensure:

- The log is on durable storage and is not deleted on deploy or restart.
- Each transaction manager instance has a stable recovery identity.
- The JMS provider and the database remain accessible when recovery runs.
- The recovery account has the necessary permissions.
- In-doubt transactions and heuristic outcomes are monitored.

If you start two transaction managers with the same recovery identity on the same set of resources without appropriate clustering configuration, recovery can cause conflicts. Follow the guidance of the transaction manager and the provider.

### Failure Testing

Do not test only the success path. You should test:

1. The JMS broker is unavailable when the producer sends.
2. The database fails after the JMS resource has already joined the transaction.
3. The listener throws an exception after it has updated the database.
4. The process stops while the transaction is preparing/committing.
5. The transaction manager restarts and performs recovery.
6. The message is redelivered and the consumer processes the same business event again.

Testing must confirm that the database data and the message state are consistent after rollback, commit, and recovery.

## 11. Costs and Limits of XA

XA delivers an atomic commit among XA-capable resources, but it has costs:

- An extra prepare round and a commit/rollback round for a multi-resource transaction.
- The transaction manager must write logs and perform recovery.
- Resources may hold locks or an in-doubt state for a long time.
- Depends on the XA capability of the broker, the JDBC driver, the pool, and the application server.
- Debugging and operations are more complex than a local transaction.
- One slow resource can slow down the whole global transaction.

Spring Framework also recommends considering a local JMS transaction combined with duplicate detection in the business logic if acceptable, because it is usually more efficient than wrapping the entire processing in XA. Choose XA when atomicity between resources is truly a mandatory requirement and the infrastructure fully supports it.

## 12. When to Use a Transactional Outbox Instead of XA?

If the database does not support XA, the JMS provider has no XA, or the organization wants to avoid the operational cost of 2PC, you can use a **Transactional Outbox**.

Flow:

~~~text
Application
    |
    | local DB transaction
    v
+-------------------------+
| orders table            |
| outbox_event table      |
+-------------------------+
    |
    | committed together
    v
Outbox Publisher
    |
    | read unsent events
    | publish via JMS
    v
JMS Broker
    |
    v
Consumer (idempotent)
~~~

In one local database transaction, the application:

1. Writes the order to the orders table.
2. Writes the event to be published to the outbox_event table.
3. Commits both together.

A separate publisher reads the unsent outbox events, sends them to JMS, and then marks them as sent. If the publisher crashes after the broker accepted the message but before marking it sent, the event may be sent again. Therefore the consumer needs idempotency based on an event ID or a stable business key.

The Transactional Outbox provides consistency between the business data and the intent to publish an event within the database. It does not create an atomic transaction directly between the database and JMS; instead, it ensures the event is stored durably so it can be republished until completion according to the retry policy.

### Comparing XA and Outbox

| Criterion | JTA/XA | Transactional Outbox |
|---|---|---|
| Mechanism | Global transaction and 2PC. | Local DB transaction + asynchronous publisher. |
| DB + JMS atomicity | Yes when both resources are XA and enlisted correctly. | Not an atomic commit with JMS; preserves the send intent in the DB. |
| Infrastructure | JTA manager, XA database, and XA JMS provider. | Ordinary database transaction, an outbox publisher, and JMS. |
| Latency | Send/receive lie within a synchronous transaction. | The event is published after the DB transaction commits. |
| Operations | Recovery log, XA resources, transaction timeouts. | Outbox cleanup, retry, publisher monitoring, and idempotency. |
| Duplicates | Still need to consider recovery and side effects outside XA. | The publisher may send duplicates; the consumer must be idempotent. |
| Suitable for | Needing an atomic commit among XA resources. | Distributed systems, a broker/database without XA support, or wanting to reduce coupling. |

An outbox is usually suitable when the application can accept event-publishing latency and design an idempotent consumer. If you need to coordinate many long business steps across multiple services, consider a Saga with compensating actions instead of holding an XA transaction for a long time.

## 13. Common Misconceptions

1. **"Having JtaTransactionManager makes every resource automatically XA."** Not true. The JMS ConnectionFactory and the DataSource must have XA support and be managed and enlisted with the same transaction coordinator.
2. **"JmsTransactionManager can coordinate the database."** Not true. It manages a local transaction for one JMS ConnectionFactory.
3. **"Calling JdbcTemplate and JmsTemplate in the same method is atomic enough."** Not true if the two templates use separate local transactions or only one transaction manager is selected.
4. **"@Transactional on the listener method automatically includes the message receive."** Not necessarily. The listener container must participate in the external JTA transaction so that the receive and the listener execution are coordinated together.
5. **"sessionTransacted=true is XA."** Not true. It is a local JMS Session transaction. XA needs a JTA manager and an XA-aware ConnectionFactory.
6. **"Every database driver supports XA."** Not true. You need to check the driver, the database, the datasource pool, and the provider configuration.
7. **"XA guarantees every external side effect is rolled back."** Not true. HTTP, email, the filesystem, and resources that are not enlisted are not in the global transaction.
8. **"2PC cannot hit an in-doubt state."** Not true. A failure after prepare may require recovery; the transaction log must be preserved.
9. **"XA completely eliminates duplicate messages."** You should not assume this for the whole system. You still need idempotency for side effects outside XA, retry, and real delivery scenarios.
10. **"You can call commit on the Session yourself inside a @Transactional method."** You should not. The JTA transaction manager must coordinate commit/rollback for the enlisted resources.
11. **"Outbox and XA are the same mechanism."** Not true. An outbox stores the intent to publish an event in a local DB transaction and then publishes asynchronously; XA coordinates an atomic commit directly among XA resources.
12. **"Just configuring the transaction timeout in Spring is enough."** Not enough. You need to align the timeouts of the JTA manager, the broker, the database, the pool, and recovery.

## 14. Takeaways

- **JTA** provides the API and the transaction manager for a global transaction.
- **XA** lets the transaction manager coordinate multiple resource managers via XAResource.
- **2PC** consists of prepare and commit/rollback; a recovery log is needed when failures occur.
- To coordinate JMS with the database, both the JMS ConnectionFactory and the DataSource must be XA-capable/JTA-managed and enlisted in the same transaction.
- **JtaTransactionManager** is the bridge between Spring's transaction abstraction and JTA.
- **JmsTransactionManager** only manages the local transaction of one JMS ConnectionFactory; it does not by itself coordinate the database.
- For a consumer, use **DefaultMessageListenerContainer** configured with an external JTA transaction so that the receive and the listener execution belong to the transaction.
- XA has costs in latency, locks, the transaction log, and recovery; use it only when the atomicity requirement justifies the cost.
- **Transactional Outbox** is a practical option when XA is not deployed; publisher retry and consumer idempotency are essential parts.
- Do not rely on XA to roll back HTTP, email, or side effects that do not participate in the transaction.

When designing JMS transactions with a database, first determine the atomicity requirement, the XA capability of each resource, where the transaction is managed, and the recovery plan. If the infrastructure cannot fully support XA, a transactional outbox usually yields an event-publishing flow that is easier to operate.

## References

- [Spring Framework 6.2 — Using Spring JMS: Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Receiving a Message: Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2 — DefaultMessageListenerContainer API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Jakarta Transactions 2.0 Specification](https://jakarta.ee/specifications/transactions/2.0/jakarta-transactions-spec-2.0.html)
- [Jakarta EE Tutorial — Jakarta Messaging Concepts and Transactions](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html)
