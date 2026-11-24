# JmsTemplate Participating in Spring Transaction Resources

## 1. The Role of JmsTemplate in a Spring Transaction

`JmsTemplate` is the high-level Spring JMS API for sending messages and receiving messages synchronously. The template manages the creation, use, and release of the Connection, Session, MessageProducer, and MessageConsumer for each operation.

When a JMS operation runs inside a Spring transaction, `JmsTemplate` can reuse the Session that the transaction manager has bound to the current thread. Multiple template calls in the same transaction can therefore commit or roll back together.

`JmsTransactionManager` manages a local transaction for one `ConnectionFactory`. When a transaction begins, the manager obtains a JMS Connection and a transacted Session, and then binds the resources to the current thread. `JmsTemplate` automatically detects and uses that Session.

~~~text
Spring transaction begins
        |
        v
JmsTransactionManager binds Connection + Session to the thread
        |
        +---- JmsTemplate.convertAndSend("orders", eventA)
        |
        +---- JmsTemplate.convertAndSend("audit", eventB)
        |
        v
Transaction commit or rollback
~~~

If the transaction rolls back, the send operations belonging to that Session are rolled back according to the JMS provider's transaction. `JmsTemplate` does not commit each send separately when it is using a Session managed by a Spring transaction.

## 2. The Transaction-Bound Resource Mechanism

`JmsTransactionManager` binds the Connection/Session pair for one specific ConnectionFactory. When `JmsTemplate` performs a send or receive, the template uses `ConnectionFactoryUtils` to obtain resources. If the thread already has a Session bound for the right ConnectionFactory, the template reuses that Session. If there is no transaction, the template manages resources itself according to the normal configuration.

When the transaction ends:

- **Commit:** the transaction manager commits the JMS Session.
- **Rollback:** the transaction manager rolls back the JMS Session.
- **Cleanup:** the Connection/Session is released or returned to the cache/pool after the transaction ends.

Resources are bound per thread. If a method inside the transaction calls `@Async`, an executor, or another worker thread, the new task does not automatically share the calling thread's Session. A background task that needs its own transaction must create its own transaction boundary. Do not pass a Session across threads.

### 2.1. The Template and the Transaction Manager Must Use the Same ConnectionFactory

`JmsTemplate` and `JmsTransactionManager` must receive the same ConnectionFactory bean. Spring uses the ConnectionFactory as the resource key to find the bound Session.

~~~java
@Bean
CachingConnectionFactory jmsConnectionFactory(
        @Qualifier("nativeConnectionFactory")
        ConnectionFactory nativeConnectionFactory) {

    CachingConnectionFactory factory =
        new CachingConnectionFactory(nativeConnectionFactory);
    factory.setSessionCacheSize(10);
    return factory;
}

@Bean
JmsTransactionManager jmsTransactionManager(
        CachingConnectionFactory jmsConnectionFactory) {
    return new JmsTransactionManager(jmsConnectionFactory);
}

@Bean
JmsTemplate jmsTemplate(
        CachingConnectionFactory jmsConnectionFactory) {
    return new JmsTemplate(jmsConnectionFactory);
}
~~~

Do not create two separate `CachingConnectionFactory` wrappers around the same native factory for the template and the manager. Two wrappers are two different resource keys; the template may not find the Session that the manager bound.

Spring recommends using `CachingConnectionFactory` with `JmsTransactionManager` to reuse Connections, Sessions, and producers efficiently. `SingleConnectionFactory` also shares a Connection, but does not cache Sessions the way CachingConnectionFactory does.

## 3. Configuring JmsTransactionManager

In a plain Spring configuration, enable transaction annotations and declare the manager together with the template:

~~~java
@Configuration
@EnableTransactionManagement
public class JmsConfiguration {

    @Bean
    CachingConnectionFactory jmsConnectionFactory(
            @Qualifier("nativeConnectionFactory")
            ConnectionFactory nativeConnectionFactory) {

        CachingConnectionFactory factory =
            new CachingConnectionFactory(nativeConnectionFactory);
        factory.setSessionCacheSize(10);
        return factory;
    }

    @Bean
    JmsTransactionManager jmsTransactionManager(
            CachingConnectionFactory jmsConnectionFactory) {
        return new JmsTransactionManager(jmsConnectionFactory);
    }

    @Bean
    JmsTemplate jmsTemplate(
            CachingConnectionFactory jmsConnectionFactory) {
        return new JmsTemplate(jmsConnectionFactory);
    }
}
~~~

`nativeConnectionFactory` is a ConnectionFactory supplied by the JMS provider, JNDI, or Spring Boot. Both `JmsTemplate` and `JmsTransactionManager` receive the `jmsConnectionFactory` bean.

If the application has multiple transaction managers, for example one manager for JDBC and one manager for JMS, give them separate names and specify the manager explicitly at the transaction boundary. Spring Boot can auto-configure the transaction infrastructure, but you need to confirm which manager is selected for each method.

## 4. Using TransactionTemplate

`TransactionTemplate` creates an explicit transaction boundary in code:

~~~java
@Service
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;
    private final TransactionTemplate transactionTemplate;

    public OrderPublisher(
            JmsTemplate jmsTemplate,
            JmsTransactionManager jmsTransactionManager) {
        this.jmsTemplate = jmsTemplate;
        this.transactionTemplate =
            new TransactionTemplate(jmsTransactionManager);
    }

    public void publish(OrderCreated event) {
        transactionTemplate.execute(status -> {
            jmsTemplate.convertAndSend("orders.queue", event);
            jmsTemplate.convertAndSend("audit.queue", event);
            return null;
        });
    }
}
~~~

The two `convertAndSend` calls use the transaction's Session. When the callback ends normally, the template requests a commit. If the callback throws a RuntimeException or marks the transaction rollback-only, the manager rolls back. The example assumes the application's MessageConverter supports the OrderCreated DTO.

You can mark a rollback explicitly:

~~~java
transactionTemplate.execute(status -> {
    jmsTemplate.convertAndSend("orders.queue", event);
    if (event.isInvalid()) {
        status.setRollbackOnly();
    }
    return null;
});
~~~

If the callback catches an exception and merely logs it, the transaction manager may see the callback end normally and commit. When the business operation fails, let the exception escape or call `status.setRollbackOnly()`.

## 5. Using @Transactional

You can use declarative transactions:

~~~java
@Service
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.queue", event);
        jmsTemplate.convertAndSend("audit.queue", event);
    }
}
~~~

The name `jmsTransactionManager` must match the bean name. When the method is invoked through the Spring proxy, the transaction interceptor starts the transaction before running the method and commits when the method completes normally.

By default, Spring rolls back on `RuntimeException` and `Error`. A checked exception does not cause a rollback under the default rule. Use `rollbackFor` if needed:

~~~java
@Transactional(
    transactionManager = "jmsTransactionManager",
    rollbackFor = BusinessException.class
)
public void publish(OrderCreated event) throws BusinessException {
    jmsTemplate.convertAndSend("orders.queue", event);
    validateOrThrow(event);
}
~~~

Notes:

- The method must be invoked through a Spring-managed proxy.
- Self-invocation does not go through the proxy in the default proxy mode.
- Do not create the service with `new` if you want Spring to apply the transaction advice.
- When there are multiple managers, specify `transactionManager` explicitly to avoid running on the wrong resource.

## 6. Which Session Does JmsTemplate Use?

When a `PlatformTransactionManager` is managing the template, `JmsTemplate` is always given a transactional JMS Session. The template's `sessionTransacted` and `sessionAcknowledgeMode` properties mainly apply when the template operates outside a Spring transaction.

| Case | Session and commit |
|---|---|
| A JmsTransactionManager manages the thread | The template uses the bound Session; the manager commits/rolls back |
| No Spring transaction, default template | Non-transacted Session with AUTO_ACKNOWLEDGE |
| No Spring transaction, sessionTransacted=true | Each template operation has its own local transacted Session and commits/rolls back per operation |

Therefore, `jmsTemplate.setSessionTransacted(true)` does not replace `JmsTransactionManager` when you need to group multiple sends in one business transaction. Do not call `commit()` or `rollback()` yourself on a Session managed by Spring.

## 7. Multiple Messages in One Transaction

If multiple sends use the same ConnectionFactory and the same transaction, they can commit or roll back together:

~~~java
@Transactional(transactionManager = "jmsTransactionManager")
public void publishOrder(OrderCreated order) {
    jmsTemplate.convertAndSend("orders.queue", order);
    jmsTemplate.convertAndSend("billing.queue", order);
    jmsTemplate.convertAndSend("audit.queue", order);
}
~~~

If the third send throws an unhandled exception, the earlier sends in the same JMS transaction are also rolled back. A consumer does not see a partial set of those messages after a successful rollback.

This mechanism only applies to JMS operations on the same transaction resource. Sending through another ConnectionFactory does not automatically participate in the transaction. A transaction also does not guarantee that a consumer processes a message exactly once; redelivery or duplicates can still occur at other boundaries. The consumer should be idempotent when the business requires it.

## 8. Receiving Messages Synchronously in a Transaction

`JmsTemplate` also supports synchronous receive. If the receive is inside a transaction managed by `JmsTransactionManager`, the receive operation uses that transacted Session:

~~~java
transactionTemplate.execute(status -> {
    OrderCommand command =
        (OrderCommand) jmsTemplate.receiveAndConvert("orders.commands");

    if (command == null) {
        return null;
    }

    orderService.process(command);
    return null;
});
~~~

On commit, the receive operation is committed. On rollback, the broker may redeliver the message according to the provider's policy. Configure an appropriate receive timeout to avoid waiting indefinitely when the queue has no messages.

`JmsTemplate.receive()` is a synchronous receive; for background message processing, a listener container such as `DefaultMessageListenerContainer` is more appropriate.

## 9. Local JMS Transaction and the Database

`JmsTransactionManager` manages a local transaction for one JMS ConnectionFactory. It does not by itself coordinate the JMS transaction with the database transaction.

~~~text
JmsTransactionManager
    -> JMS Session transaction

DataSourceTransactionManager
    -> JDBC Connection transaction
~~~

Using two separate local transaction managers does not create one atomic transaction spanning both JMS and the database. One resource can commit while the other fails.

The options:

- **JTA/XA:** use `JtaTransactionManager` together with an XA-capable JMS ConnectionFactory and an XA datasource registered with the same transaction coordinator.
- **Outbox pattern:** write the business data and an outbox record in the same database transaction; a separate publisher reads the outbox and sends the message.
- **Eventual consistency:** design retry, idempotency, and reconciliation when the business accepts eventual consistency.

Do not call `JmsTransactionManager` XA. A local JMS transaction only manages the JMS resource the manager is responsible for.

### 9.1. JTA/XA with JmsTemplate

When you need a distributed transaction, configure `JtaTransactionManager` and an XA-capable ConnectionFactory:

~~~java
@Bean
JtaTransactionManager transactionManager() {
    return new JtaTransactionManager();
}

@Transactional(transactionManager = "transactionManager")
public void createOrder(Order order) {
    orderRepository.save(order);
    jmsTemplate.convertAndSend("orders.queue", toEvent(order));
}
~~~

The example is only atomic in meaning when both the datasource and the JMS ConnectionFactory are configured for XA, registered with the same transaction coordinator, and the provider supports the necessary operations. Merely renaming the transaction manager to JTA is not enough. XA has coordination and transaction-log costs; if you do not need an atomic multi-resource commit, an Outbox is usually easier to operate.

## 10. Using the JMS API Directly

Prefer `JmsTemplate` because the template obtains the transactional Session itself. Code that directly calls `ConnectionFactory.createConnection()` and `Connection.createSession()` does not automatically find the Session that `JmsTransactionManager` has bound.

You can:

1. Use `ConnectionFactoryUtils.getTransactionalSession(...)` to obtain a Session that participates in the transaction.
2. Wrap the target factory with `TransactionAwareConnectionFactoryProxy` if legacy code needs to call ConnectionFactory/Connection/Session in the ordinary JMS style.

`TransactionAwareConnectionFactoryProxy` should be the outermost adapter of the proxy chain. For new code, the template usually helps reduce resource lifecycle errors.

## 11. Reusing Connections and Sessions

`JmsTransactionManager` holds one Connection/Session pair throughout the transaction. The Session belongs to the current thread and transaction; do not share the Session with another thread.

`CachingConnectionFactory` can share the physical Connection, cache Sessions by acknowledgment/transaction mode, and cache producers/consumers according to configuration. Each transaction still has its own Session. Sharing a Connection does not mean transactions share a Session or commit together.

When using the cache, close the Session proxy with the correct lifecycle so that the Session is returned to the cache. Do not hold a Session in a singleton bean or share one Session among multiple threads.

## 12. Testing JmsTemplate Transactions

Tests should confirm commit and rollback with a real JMS provider or an embedded broker:

1. Begin a Spring JMS transaction.
2. Send a message and then mark it rollback-only.
3. End the transaction.
4. Try to receive the message; the result must be null if the rollback succeeded.
5. Send a message in a transaction that commits.
6. Receive the message again and confirm the payload is correct.

Mocking `JmsTemplate` does not prove that the broker actually rolls back or commits the message. Add tests for exceptions, multiple sends in the same transaction, and the real provider configuration.

## 13. A Java 17+ Example Running with an Embedded Artemis Broker

The example uses an embedded Artemis broker, `JmsTransactionManager`, `TransactionTemplate`, and `JmsTemplate`. The program sends one message in a rollback-only transaction, then sends one message that is committed and reads the results.

**Project structure**

~~~text
jmstemplate-tx-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          JmsTemplateTransactionDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jmstemplate-tx-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
            <version>2.37.0</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.37.0</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/JmsTemplateTransactionDemo.java**

~~~java
package demo;

import org.apache.activemq.artemis.core.config.impl.ConfigurationImpl;
import org.apache.activemq.artemis.core.server.embedded.EmbeddedActiveMQ;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.jms.connection.JmsTransactionManager;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class JmsTemplateTransactionDemo {

    public static void main(String[] args) throws Exception {
        EmbeddedActiveMQ broker = new EmbeddedActiveMQ();
        broker.setConfiguration(new ConfigurationImpl()
            .setPersistenceEnabled(false)
            .setSecurityEnabled(false)
            .addAcceptorConfiguration("netty", "tcp://127.0.0.1:61617"));
        broker.start();

        ActiveMQConnectionFactory connectionFactory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61617");

        try {
            JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
            jmsTemplate.setReceiveTimeout(500);

            JmsTransactionManager transactionManager =
                new JmsTransactionManager(connectionFactory);
            TransactionTemplate transactionTemplate =
                new TransactionTemplate(transactionManager);

            boolean[] resourceBound = new boolean[1];

            transactionTemplate.execute(status -> {
                resourceBound[0] =
                    TransactionSynchronizationManager.hasResource(connectionFactory);
                jmsTemplate.convertAndSend("tx.queue", "rolled-back");
                status.setRollbackOnly();
                return null;
            });

            String afterRollback =
                (String) jmsTemplate.receiveAndConvert("tx.queue");

            jmsTemplate.convertAndSend("tx.queue", "committed");

            String afterCommit =
                (String) jmsTemplate.receiveAndConvert("tx.queue");

            System.out.println("resourceBoundInsideTransaction=" + resourceBound[0]);
            System.out.println("messageAfterRollback=" + afterRollback);
            System.out.println("messageAfterCommit=" + afterCommit);
        }
        finally {
            connectionFactory.close();
            broker.stop();
        }
    }
}
~~~

Run from the `jmstemplate-tx-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JmsTemplateTransactionDemo
~~~

**Output from the program**

~~~text
resourceBoundInsideTransaction=true
messageAfterRollback=null
messageAfterCommit=committed
~~~

Explanation:

- `resourceBoundInsideTransaction=true` shows that Spring has bound the ConnectionFactory's resource to the thread within the transaction.
- `messageAfterRollback=null` shows that the message sent in the rollback-only transaction does not appear in the queue.
- `messageAfterCommit=committed` shows that a successfully committed message can be received again.

The example uses an embedded Artemis with the default auto-create queue. A production broker needs its own ConnectionFactory, credentials, TLS, destination, and transaction policy configuration. Logging/native library warnings may appear depending on the environment; the three lines above are the output printed by the program.

## 14. Common Mistakes

1. **Two different ConnectionFactory wrappers:** the template does not find the Session that the transaction manager bound.
2. **Thinking JmsTemplate opens a business transaction itself:** without a manager, each operation follows the template's Session configuration.
3. **Using sessionTransacted=true instead of a manager:** each call may be its own transaction and does not group multiple sends in a method.
4. **Calling the raw ConnectionFactory:** creating a Session directly does not automatically participate in the transaction-bound resource; use ConnectionFactoryUtils or TransactionAwareConnectionFactoryProxy.
5. **Catching and swallowing the exception:** the transaction may commit if the callback ends normally.
6. **Assuming a checked exception always rolls back:** use rollbackFor if you need to roll back on a checked exception.
7. **Assuming JmsTransactionManager coordinates the database:** this is a local transaction for one JMS ConnectionFactory; you need JTA/XA for a distributed atomic commit.
8. **Calling commit/rollback yourself on Spring's Session:** let the transaction manager control it.
9. **Sharing a Session across threads:** each transaction needs its own Session.
10. **Forgetting the @Transactional proxy:** self-invocation or an object created with new can bypass the transaction advice.
11. **Not specifying the manager when there are multiple managers:** the method may run on the wrong resource.
12. **Confusing a committed send with the consumer having processed it:** the consumer has its own transaction and result.
13. **Testing only with mocks:** a mock does not prove that the broker actually rolls back/commits.
14. **Ignoring idempotency:** retry/redelivery can create duplicate messages.

## 15. Configuration Checklist

1. Is there an appropriate `JmsTransactionManager` or JTA transaction manager?
2. Do the template and the manager use the same ConnectionFactory bean?
3. Is there a clear transaction boundary through `TransactionTemplate` or `@Transactional`?
4. Is the transactional method invoked through the Spring proxy?
5. Are the rollback rules for RuntimeException and checked exceptions correct for the requirements?
6. Do you distinguish a local JMS transaction from a database/XA transaction?
7. Does the ConnectionFactory have caching/pooling appropriate for the load?
8. Do you avoid using a Session concurrently from multiple threads?
9. Do you test both commit and rollback against a broker?
10. Is the consumer idempotent, and do you monitor redelivery/dead-letter?

## 16. Conclusion

`JmsTransactionManager` binds a Connection/Session pair of the JMS ConnectionFactory to the thread. `JmsTemplate` automatically detects and uses that Session, so multiple send/receive operations can commit or roll back in the same JMS transaction.

For the mechanism to work correctly, the template and the transaction manager must use the same ConnectionFactory bean, the transaction boundary must be managed by Spring, and exceptions must be handled according to the defined rollback rules. `JmsTransactionManager` only manages a local JMS transaction; to get atomicity between JMS and the database you need JTA/XA or a design such as the Outbox.

## 17. References

- [Spring Framework 6.2 — Using Spring JMS: Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [JmsTransactionManager — Spring Framework 6.2.18 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [JmsTemplate — Spring Framework 6.2.18 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [ConnectionFactoryUtils — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/connection/ConnectionFactoryUtils.html)
- [TransactionAwareConnectionFactoryProxy — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/connection/TransactionAwareConnectionFactoryProxy.html)
- [Spring Framework 6.2 — Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction.html)
- [Spring Framework 6.2 — Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html)