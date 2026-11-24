# JmsTransactionManager and a Single ConnectionFactory in Spring JMS

## 1. What Problem Does JmsTransactionManager Solve?

JMS can send messages through multiple operations within the same business operation. For example, when creating an order, the application may send an event to orders.queue and at the same time send a notification record to audit.queue. If the second send fails, the application usually wants to cancel both send operations.

Spring provides JmsTransactionManager to manage a local transaction for one JMS ConnectionFactory. When a transaction begins, the manager obtains a JMS Connection and a transacted Session, and then binds this resource pair to the current thread. JMS operations that use the same ConnectionFactory in that thread can participate in the same transaction.

JmsTemplate automatically detects the Session that Spring has bound to the thread and reuses that Session. Therefore, the application can write multiple convertAndSend or send commands in one business method without having to create a Connection or Session or call commit itself.

One thing to understand clearly: JmsTransactionManager manages a transaction for one ConnectionFactory. It does not by itself coordinate multiple brokers or multiple different resources into one distributed transaction.

## 2. How Are the Connection, Session, and Transaction Linked?

In JMS, the Connection represents the connection to the provider. The Session is the working context that holds send and receive operations and the transaction. With a JMS transaction, messages sent or received on the same Session are committed or rolled back together.

JmsTransactionManager performs these main steps:

1. Begin the transaction according to the Spring configuration.
2. Create or obtain a Connection from the managed ConnectionFactory.
3. Create a transacted Session.
4. Bind the Connection and Session to the current thread, keyed by the ConnectionFactory.
5. Let JmsTemplate or Spring-integrated code retrieve the bound Session.
6. When the business method ends, commit if it succeeded or roll back if the transaction is marked rollback-only.
7. Release resources and unbind the thread after the transaction completes.

You can picture the flow as follows:

~~~mermaid
sequenceDiagram
    participant S as Service
    participant TM as JmsTransactionManager
    participant CF as ConnectionFactory
    participant JT as JmsTemplate
    participant JMS as JMS Provider

    S->>TM: begin transaction
    TM->>CF: create Connection
    CF-->>TM: Connection
    TM->>CF: create transacted Session
    CF-->>TM: Session
    TM->>TM: bind Session to current thread
    S->>JT: convertAndSend orders.queue
    JT->>TM: find transactional Session
    TM-->>JT: bound Session
    JT->>JMS: send message
    S->>JT: convertAndSend audit.queue
    JT->>JMS: send message using same Session
    S->>TM: method completes
    TM->>JMS: commit or rollback
    TM->>TM: unbind and release resources
~~~

Two messages can be sent to two different destinations and still belong to the same transaction if both operations use the same ConnectionFactory and the same transaction-bound Session.

## 3. Why Must You Use the Same ConnectionFactory?

The ConnectionFactory is the key Spring uses to find the JMS resources bound to a transaction. JmsTransactionManager registers the Connection and Session by the ConnectionFactory it manages. When JmsTemplate needs a Session, it also looks up resources by the ConnectionFactory that the template is using.

Therefore, a correct configuration must ensure:

- JmsTransactionManager receives one ConnectionFactory.
- JmsTemplate receives that same ConnectionFactory bean.
- The JMS operations that need to participate in the transaction run in the same thread and within the scope of the active transaction.

For example, the manager uses the jmsConnectionFactory bean but the JmsTemplate uses a different wrapper or uses providerConnectionFactory directly. In that case Spring may not find the Session bound under the manager's ConnectionFactory key. The send command may create its own Session and not be in the intended transaction.

Using the same broker or the same server address is not enough. Share the same Spring ConnectionFactory bean that is configured for the transaction.

## 4. CachingConnectionFactory in a Standalone Configuration

The JmsTransactionManager documentation strongly recommends using CachingConnectionFactory as the manager's target ConnectionFactory. CachingConnectionFactory keeps one shared JMS Connection and caches Sessions, MessageProducers, and MessageConsumers. Each transaction still has its own Session; the Session is returned to the cache after the transaction completes.

This reduces the cost of repeatedly creating Connections and helps manage the producer/consumer lifecycle more efficiently. The default sessionCacheSize value is 1 for each kind of Session acknowledgement. When the application has many concurrent transactions, you can increase the cache size after measuring the real load.

Distinguish two ideas:

- Sharing one ConnectionFactory bean does not mean all transactions share one Session.
- Concurrent transactions must have their own Sessions because a JMS Session must not be used concurrently from multiple threads.

In a Jakarta EE environment that already has a container-managed ConnectionFactory with Connection/Session pooling, use the resource supplied by the container following the provider's guidance. In a standalone application, CachingConnectionFactory is the Spring choice that JmsTransactionManager recommends as the target.

## 5. Configuring a Shared ConnectionFactory

The following example assumes the JMS provider has supplied a providerConnectionFactory bean. This bean contains the specific broker configuration such as the connection address, credentials, TLS, and provider-specific options.

The application creates a single CachingConnectionFactory named jmsConnectionFactory. Both JmsTransactionManager and JmsTemplate inject that bean.

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.CachingConnectionFactory;
import org.springframework.jms.connection.JmsTransactionManager;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class JmsTransactionConfiguration {

    @Bean
    public CachingConnectionFactory jmsConnectionFactory(
            @Qualifier("providerConnectionFactory")
            ConnectionFactory providerConnectionFactory) {

        CachingConnectionFactory connectionFactory =
            new CachingConnectionFactory(providerConnectionFactory);

        connectionFactory.setSessionCacheSize(10);
        return connectionFactory;
    }

    @Bean
    public JmsTransactionManager jmsTransactionManager(
            @Qualifier("jmsConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new JmsTransactionManager(connectionFactory);
    }

    @Bean
    public JmsTemplate jmsTemplate(
            @Qualifier("jmsConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new JmsTemplate(connectionFactory);
    }
}
~~~

In this configuration, jmsConnectionFactory is a single Spring bean. The manager and the template both receive that bean through Qualifier. Setting sessionCacheSize to 10 is only an example for concurrent load; adjust it according to the number of transactions and the broker's resource limits.

Do not create two separate CachingConnectionFactory instances, one for the manager and one for the template, even if both wrap the same providerConnectionFactory. Two wrappers are two different ConnectionFactory objects as far as Spring's transaction resource lookup is concerned.

## 6. Sending Multiple Messages in One Transaction

After configuring the manager and the template, you can use declarative transactions via @Transactional.

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void publish(String orderId, boolean forceRollback) {
        jmsTemplate.convertAndSend("orders.queue", orderId);

        jmsTemplate.convertAndSend(
            "audit.queue",
            "created:" + orderId
        );

        if (forceRollback) {
            throw new IllegalStateException("Demo rollback");
        }
    }
}
~~~

When the publish method ends normally, Spring commits the JMS transaction. Both messages are committed on the same Session.

If forceRollback is true, the method throws an IllegalStateException. This is a RuntimeException, so by default Spring marks the transaction for rollback. The two send operations in the Session are rolled back together under the transaction contract of the JMS provider.

If the method throws a checked exception, by default @Transactional does not roll back merely because of a checked exception. Declare an appropriate rollbackFor if the business operation needs a rollback in that case:

~~~java
@Transactional(
    transactionManager = "jmsTransactionManager",
    rollbackFor = Exception.class
)
public void publishWithCheckedFailure(String orderId) throws Exception {
    jmsTemplate.convertAndSend("orders.queue", orderId);
    throw new Exception("Rollback the JMS transaction");
}
~~~

Only a method invoked through the Spring proxy gets the transaction interceptor applied. A self-call to another @Transactional method in the same object usually does not go through the proxy and therefore does not open a transaction as expected.

## 7. Transaction Propagation and Thread Binding

By default @Transactional uses the REQUIRED propagation. If there is already a transaction managed by this JmsTransactionManager, the next call participates in the current transaction. If there is none, Spring opens a new transaction.

The JMS resource is bound to the thread. Therefore, JmsTemplate commands in the same thread and the same transaction scope can reuse the Session. If you move work to @Async, an executor, CompletableFuture, or create a new thread, the transaction context does not automatically follow to the new thread.

Example:

~~~java
@Transactional(transactionManager = "jmsTransactionManager")
public void publish(String orderId) {
    jmsTemplate.convertAndSend("orders.queue", orderId);

    // If you call a task on another thread, that task does not automatically
    // participate in the Session transaction bound to the current thread.
}
~~~

If an asynchronous task needs its own transaction, open a new transaction inside that task with an appropriate transaction manager. Do not pass a JMS Session that another transaction is using to a different thread.

## 8. Using JmsTransactionManager with the Plain JMS API

JmsTemplate already detects the Session bound to the thread. For legacy code that calls ConnectionFactory.createConnection() directly and then creates a Session, that usage does not automatically participate in a Spring transaction.

There are two options:

1. Obtain a transactional Session through ConnectionFactoryUtils.getTransactionalSession.
2. Wrap the ConnectionFactory with TransactionAwareConnectionFactoryProxy so that legacy code can keep using the standard JMS call style but can participate in a Spring-managed transaction.

Example of declaring the proxy for legacy code:

~~~java
@Bean
public TransactionAwareConnectionFactoryProxy transactionAwareConnectionFactory(
        @Qualifier("jmsConnectionFactory")
        ConnectionFactory connectionFactory) {

    return new TransactionAwareConnectionFactoryProxy(connectionFactory);
}
~~~

This proxy uses as its target the same jmsConnectionFactory that JmsTransactionManager manages. When legacy code closes the Connection or Session, the proxy adjusts the close operation so that it does not close the transaction's resources before the transaction completes.

For new code, prefer JmsTemplate or ConnectionFactoryUtils so that Spring manages the Session lifecycle explicitly.

## 9. What Scope Does JmsTransactionManager Manage?

JmsTransactionManager is the local transaction manager for one ConnectionFactory. Different destinations can still be in the same transaction if they are accessed through the same ConnectionFactory and the same Session.

| Situation | Can it be in the same local JMS transaction? |
| --- | --- |
| Send to orders.queue and audit.queue through the same JmsTemplate | Yes |
| Two JmsTemplates using the same jmsConnectionFactory bean | Yes |
| The manager uses CachingConnectionFactory A, the template uses CachingConnectionFactory B | Not guaranteed; Spring resources are looked up by ConnectionFactory |
| Send through two brokers with two different ConnectionFactories | No |
| Send JMS and update the database via JDBC in the same JmsTransactionManager @Transactional method | The database is not automatically part of the JMS transaction |
| Use JTA/XA with an XA-capable JMS ConnectionFactory and an XA database resource | Can be coordinated in a distributed transaction if the infrastructure is configured correctly |

If a method sends messages through two different ConnectionFactories, JmsTransactionManager cannot commit or roll back both as one atomic unit. Each factory needs its own transaction manager and transaction, or the application needs a suitable distributed solution.

## 10. The Boundary Between a Local JMS Transaction and a Database Transaction

A JMS local transaction only manages operations on the JMS Session. It does not automatically include JDBC, JPA, the filesystem, or another broker.

For example, if a service updates the database and then sends JMS:

1. The database transaction may commit successfully.
2. The JMS commit may fail afterwards.
3. The database has saved the state but the message was not sent.

The opposite case can also occur if the two resources commit in a different order. Putting two operations in the same Java method or under the same @Transactional annotation does not turn them into a distributed transaction.

If you need an atomic commit between JMS and the database, use JtaTransactionManager together with an XA-capable ConnectionFactory and an XA-aware database resource, and configure the transaction coordinator and the broker correctly. XA has higher operational cost, transaction log, and recovery overhead than a local transaction.

For many systems, a transactional outbox is the appropriate choice: write the business data and an outbox record in the same database transaction, and then a separate publisher sends the outbox to the broker. The consumer should still be idempotent to handle duplicates.

## 11. JmsTransactionManager and the Listener Container

JmsTransactionManager is usually used for transactions that a service opens via @Transactional or TransactionTemplate. The transaction for receiving messages in a listener container has its own configuration.

With DefaultMessageListenerContainer, if you only need a local JMS transaction for each message the listener processes, you can enable sessionTransacted. When the listener throws an exception, the message receipt can be rolled back and the broker redelivers according to the provider's policy.

~~~java
@Bean
public DefaultMessageListenerContainer ordersListenerContainer(
        ConnectionFactory jmsConnectionFactory,
        Destination ordersQueue,
        MessageListener orderListener) {

    DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

    container.setConnectionFactory(jmsConnectionFactory);
    container.setDestination(ordersQueue);
    container.setMessageListener(orderListener);
    container.setSessionTransacted(true);
    return container;
}
~~~

The sessionTransacted configuration creates a local JMS transaction in the container's Session. It does not by itself coordinate a database transaction. If you need message receipt, listener processing, and the database to commit together via XA, configure the container with JtaTransactionManager and XA-capable resources following Spring's guidance.

Do not confuse the transaction that JmsTransactionManager opens for a service with the internal transaction that the listener container manages. Choose a clear strategy for each receive and send flow.

## 12. Transaction Synchronization

JmsTransactionManager turns off transaction synchronization by default. The reason is that the application may use this manager together with a transaction manager for a datastore, such as DataSourceTransactionManager, and only one manager is allowed to drive Spring transaction synchronization at a time.

Spring has a mechanism that lets a local JMS transaction be synchronized with another Spring-managed transaction in some cases. However, the JMS transaction commits after the main transaction; that is not XA and does not guarantee that the two resources commit atomically.

When you need consistency across multiple resources, define clearly the commit, rollback, and recovery mechanism. Do not rely on two managers running in the same call stack to infer that they are managing a shared transaction.

## 13. Common Mistakes

| Symptom | Cause | How to fix |
| --- | --- | --- |
| The message is still sent even though the service rolled back | JmsTemplate uses a different ConnectionFactory than the manager | Inject the same jmsConnectionFactory bean into both |
| Of two messages, only one is rolled back | One send command uses its own Session or ConnectionFactory | Check all templates and plain JMS code |
| JmsTemplate does not find the transaction | There is no active transaction, or the command runs on another thread | Check the @Transactional proxy, the selected manager, and the executing thread |
| @Transactional has no effect | An internal call within the same object so it does not go through the proxy | Call through another Spring bean or use TransactionTemplate |
| The database commits but JMS rolls back | A local JMS transaction is used together with a JDBC transaction | Use an outbox or JTA/XA if you need an atomic commit |
| JMS commits but the database rolls back | The two resources are managed independently | Design an outbox/idempotency or a distributed transaction |
| The JMS provider fails on commit | The driver has an incompatible close producer/consumer behavior or resources are not cached appropriately | Use CachingConnectionFactory as the target per Spring's recommendation and check the provider |
| Session resources are not reused | The session cache is too small or the code does not close the Session properly | Adjust sessionCacheSize and close resources through the proper API |
| Duplicate message after a JVM failure | The broker may redeliver when the commit has not completed or the acknowledgment state is unclear | Use an event ID and process idempotently |
| Multiple transactions share one Session | The code holds and shares the Session across threads | Let the manager manage a separate Session for each transaction |

## 14. Production Configuration Checklist

- [ ] Choose one ConnectionFactory bean as the JMS resource the manager manages.
- [ ] Inject exactly that same bean into JmsTransactionManager and every JmsTemplate that needs to participate in the transaction.
- [ ] For a standalone application, consider CachingConnectionFactory as the target per Spring's recommendation.
- [ ] Choose sessionCacheSize based on concurrency and measure the real load.
- [ ] Enable @EnableTransactionManagement if using @Transactional in plain Spring Framework.
- [ ] Explicitly specify the transactionManager when the application has multiple PlatformTransactionManagers.
- [ ] Keep the operations that must share a transaction in the same thread.
- [ ] Define the rollback rules for checked exceptions explicitly.
- [ ] Do not use JmsTransactionManager to assume that JDBC or another broker commits atomically with it.
- [ ] Use JtaTransactionManager and XA resources when a distributed transaction is truly needed.
- [ ] Consider a transactional outbox and an idempotent consumer to handle duplicates.
- [ ] Test commit, rollback, broker restart, commit errors, and resource limits.
- [ ] Monitor transaction duration, commit/rollback failures, active sessions, connection pool, and redelivery count.

## 15. References

- [Spring Framework 7.0.10 API — JmsTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [Spring Framework 7.0.10 API — CachingConnectionFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html)
- [Spring Framework 7.0.10 API — ConnectionFactoryUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/ConnectionFactoryUtils.html)
- [Spring Framework — Using Spring JMS: Transaction Management](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — Receiving a Message: Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
