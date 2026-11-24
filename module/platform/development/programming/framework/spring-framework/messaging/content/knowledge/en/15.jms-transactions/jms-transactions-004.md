# sessionTransacted and Local Transactions on a Session

JMS lets you group message send and receive operations into a single transaction. When a Session is created in transacted mode, the application decides when to complete the group of operations with commit() or cancel it with rollback(). Spring JMS supports managing this transaction through JmsTemplate, JmsTransactionManager, and the message listener container.

The boundary of a local transaction is one JMS Session. Messages received and messages sent on the same Session are acknowledged or rolled back together. This transaction does not automatically span database operations, HTTP, or another JMS ConnectionFactory.

This lesson explains how a Session transaction works, compares it with the acknowledgment mode, shows how to configure Spring, how to handle redelivery, and how to test it with a Java 17 program that connects to Apache ActiveMQ Artemis.

## 1. What Is a Local Transaction on a JMS Session?

A JMS Session is the working context in which the application creates Messages, MessageProducers, and MessageConsumers. When the Session is created in transacted mode, the message send and receive operations are grouped into a local transaction.

Create a transacted Session with Jakarta Messaging:

~~~java
Session session = connection.createSession(true, Session.SESSION_TRANSACTED);
~~~

With a transacted Session:

- A message sent in an uncommitted transaction is not yet confirmed as successfully sent to the receiving flow.
- A message received in an uncommitted transaction still belongs to the open transaction.
- commit() completes the transaction: sent messages are committed and received messages are acknowledged.
- rollback() cancels the transaction: sent messages are discarded and received messages are returned to a state where they can be redelivered.

Example of one processing pass:

~~~text
Consumer receives Order #1024
          |
          v
Validate and process the order
          |
          +---- Success ----> session.commit()
          |                         |
          |                         +--> Message is acknowledged
          |
          +---- Error --------> session.rollback()
                                    |
                                    +--> Message may be redelivered
~~~

The transaction is managed by the provider/broker according to the JMS contract. The application does not write the message state into a database to simulate a commit.

## 2. What Do commit() and rollback() Affect?

A JMS transaction on a Session can include both sent messages and received messages. This is an important benefit of a transacted Session.

| Operation in the same Session | commit() | rollback() |
|---|---|---|
| Send a message | The message is committed and can be delivered | The sent message is discarded and not delivered from this transaction |
| Receive a message | The message is acknowledged | The message may be redelivered |
| Receive then send a reply | The receive and send are completed in the same transaction | The receive is undone and the reply is discarded |
| Multiple messages sent/received | Completed together | Rolled back together |

For example, a consumer receives an order and then sends an OrderProcessed event. If both the receive and the send happen on the same transacted Session, a single commit acknowledges the order receipt and sends the response event in the same JMS transaction.

If processing fails and rolls back, the broker may redeliver the order and does not publish the OrderProcessed event that was sent in the canceled transaction.

An important condition is that the operations must really use the same Session. If the producer and the consumer use two different Sessions, each Session has its own transaction, even when they belong to the same Connection.

## 3. The Scope of a Transaction Is One Session

A JMS Connection can create multiple Sessions. Each transacted Session manages its own transaction.

~~~text
JMS Connection
    |
    +---- Session A (transaction A)
    |         |
    |         +---- Producer A
    |         +---- Consumer A
    |
    +---- Session B (transaction B)
              |
              +---- Producer B
              +---- Consumer B
~~~

If Session A commits, the transaction of Session B does not automatically commit with it. Likewise, rolling back Session A does not undo messages already committed on Session B.

This also applies when two Sessions share one physical Connection. Sharing a Connection does not mean sharing a transaction.

In practice, a processing flow usually uses a Session managed by Spring or the JMS provider. Do not share a transacted Session among multiple threads. A Session and the producers/consumers created from it must be used serially according to the Jakarta Messaging rules.

## 4. How Does a Session Transaction Differ from an Acknowledgment Mode?

When creating a non-transacted Session, the application chooses an acknowledgment mode:

| Mode | Behavior |
|---|---|
| AUTO_ACKNOWLEDGE | The provider acknowledges the message automatically according to the rules of the mode |
| CLIENT_ACKNOWLEDGE | The client explicitly calls acknowledge() |
| DUPS_OK_ACKNOWLEDGE | Allows the provider to acknowledge in groups and possibly deliver duplicates |
| SESSION_TRANSACTED | The Session uses a local transaction; commit/rollback control acknowledgment and recovery |

With a transacted Session, the acknowledgment mode no longer controls the acknowledgment of messages. commit() performs the acknowledgment; rollback() performs the recovery. There is no need to call message.acknowledge() in a transacted Session.

With CLIENT_ACKNOWLEDGE, one acknowledge() call on a message can acknowledge all messages the Session has previously consumed. This is not a transaction mechanism that includes sent messages.

If you need an atomic group of receive and send operations within the scope of JMS, a transacted Session is the clearer choice.

### Why Might AUTO_ACKNOWLEDGE Not Be Reliable Enough?

In some kinds of listener container, the message may be acknowledged before the listener completes the business operation. If the listener throws an exception afterwards, the broker does not necessarily redeliver the message.

Spring recommends using a transacted Session when you need reliability for receiving messages. With a listener container, configuring sessionTransacted=true places receiving and listener processing inside a local JMS transaction.

## 5. Creating and Using a Transacted Session with Jakarta Messaging

To begin a local transaction, the application creates the Session in SESSION_TRANSACTED mode:

~~~java
Session session = connection.createSession(true, Session.SESSION_TRANSACTED);
~~~

After that, every send and receive operation through this Session participates in the open transaction.

Send a message and commit:

~~~java
TextMessage message = session.createTextMessage("Order #1024");
producer.send(message);
session.commit();
~~~

Receive a message and commit:

~~~java
Message received = consumer.receive(5000);

if (received != null) {
    // Business processing succeeded.
    session.commit();
}
~~~

If processing fails:

~~~java
try {
    Message received = consumer.receive(5000);

    if (received != null) {
        process(received);
        session.commit();
    }
}
catch (Exception ex) {
    session.rollback();
    throw ex;
}
~~~

In a real application, you need to decide clearly which exceptions must trigger a rollback. Do not swallow an exception and then commit, because the message would still be acknowledged even though the business operation is not complete.

The commit() and rollback() methods are only for transacted Sessions managed by the application. Calling them on a non-transacted Session causes an IllegalStateException.

When closing a Session that still has an uncommitted transaction, Jakarta Messaging specifies that the open transaction is rolled back. Therefore, try-with-resources helps release resources but does not replace an explicit commit when the business operation succeeds.

## 6. A Local Transaction Does Not Automatically Include the Database

Suppose a listener receives a message and updates the database:

~~~text
JMS Broker
    |
    | receives OrderCreated
    v
JMS Session transaction
    |
    +----> Database transaction
    |         |
    |         +---- UPDATE orders
    |         +---- COMMIT database
    |
    +----> JMS commit
~~~

If the database commit succeeds but the JMS commit fails, the broker may redeliver the message. The listener will receive the same event again and risks updating the data a second time.

If the JMS commit succeeds but the database transaction fails, the message has been acknowledged while the business data was not saved.

A JMS local transaction only manages the JMS resources on the corresponding Session/ConnectionFactory. It does not by itself create a distributed transaction with the database.

There are three common design directions:

**Idempotency and duplicate detection:** store an event ID or business operation ID in the database. Before performing an update, check whether the event has already been processed. If the broker redelivers the message, the operation that completed earlier is not repeated.

**Outbox/inbox pattern:** write the business change and the event record in the same database transaction. A separate process publishes events from the outbox. The receiving side can store the event ID in an inbox to prevent duplicate processing. This is usually easier to operate than XA in many service-based systems.

**XA/JTA transaction:** use a transaction coordinator and XA-capable resources to bring JMS and the database into the same distributed transaction. This requires more complex configuration, a transaction log, and support from both the provider and the database.

Do not claim exactly-once merely because sessionTransacted is enabled. Redelivery and duplicates can still appear at failure boundaries or when the commit result is unclear.

## 7. Local Transactions with JmsTemplate

JmsTemplate supports the sessionTransacted property. When enabled, the template creates a transacted Session for the operation if there is no externally managed transaction.

Configuration:

~~~java
@Bean
public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setSessionTransacted(true);
    return template;
}
~~~

When calling:

~~~java
jmsTemplate.convertAndSend("orders.queue", "Order #1024 created");
~~~

Spring performs the send operation on a transacted Session and completes the transaction following the template operation's lifecycle. If an error occurs in the operation, the local transaction is rolled back.

If you need multiple JMS commands to participate in one transaction, you can use JmsTransactionManager.

### JmsTransactionManager

JmsTransactionManager manages a local transaction for one ConnectionFactory. It binds the Connection/Session pair participating in the transaction to the current thread. JmsTemplate recognizes the bound resource and uses that Session.

Declare the transaction manager:

~~~java
@Bean
public JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {

    return new JmsTransactionManager(connectionFactory);
}
~~~

A service can send multiple messages in the same transaction:

~~~java
@Service
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void publishOrder(String orderId) {
        jmsTemplate.convertAndSend(
                "orders.events",
                "OrderCreated:" + orderId
        );

        jmsTemplate.convertAndSend(
                "audit.events",
                "OrderCreated:" + orderId
        );
    }
}
~~~

When the method completes normally, the transaction manager commits the JMS transaction. If the method throws a RuntimeException, the transaction is rolled back according to Spring's default rollback rules. For checked exceptions, configure rollbackFor if the business operation requires a rollback.

The two send commands use the same JMS resource bound to the thread, so they belong to the same local transaction if they share the same ConnectionFactory and the same transaction manager.

JmsTransactionManager only manages one ConnectionFactory. It does not by itself turn database or HTTP commands in the same method into part of the JMS transaction.

## 8. Local Transactions in the Listener Container

For a message listener, Spring can open a local JMS transaction for each listener invocation with sessionTransacted=true.

Factory configuration:

~~~java
@Bean
public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-6");

    return factory;
}
~~~

Listener:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void handle(String payload) {
        processOrder(payload);
    }

    private void processOrder(String payload) {
        System.out.println("Processing " + payload);
    }
}
~~~

With this configuration, each listener invocation runs in a JMS Session transaction:

1. The container receives the message.
2. Spring calls the listener method.
3. If the listener completes normally, the container commits.
4. If the listener throws an exception, the container rolls back.
5. The broker may redeliver the message according to the redelivery policy.

The rollback and redelivery mechanism also depends on the broker configuration, the redelivery limit, and the dead-letter address/queue. After the maximum number of attempts, the broker usually moves the message to a dead-letter destination according to the configured policy.

If the listener needs to send a reply using SessionAwareMessageListener, the send operation on the Session provided to the listener can belong to the same local transaction. Database operations remain independent unless there is an appropriate transaction manager.

### DMLC and SMLC

Both DefaultMessageListenerContainer and SimpleMessageListenerContainer support native JMS transactions through sessionTransacted.

DefaultMessageListenerContainer is usually used when you need recovery, flexible concurrency, or an external transaction manager. SimpleMessageListenerContainer keeps a fixed number of consumers and relies on the JMS provider's callback.

When you require reliable redelivery, enable sessionTransacted=true or configure an appropriate external transaction manager. The default AUTO_ACKNOWLEDGE does not provide the same rollback guarantee when the listener fails.

## 9. Distinguishing sessionTransacted, JmsTransactionManager, and XA/JTA

These three configurations are related but have different boundaries:

| Mechanism | Scope | Who decides commit/rollback? |
|---|---|---|
| Session transacted | One JMS Session | The application or Spring manages the Session |
| JmsTransactionManager | One JMS ConnectionFactory, local transaction bound to the thread | Spring PlatformTransactionManager |
| XA/JTA | Multiple XA resources such as JMS and the database | The JTA transaction coordinator |

### sessionTransacted=true

Use it when you need a local transaction for one template operation or one listener invocation. No external transaction coordinator is needed.

### JmsTransactionManager

Use it when a service needs multiple JMS operations to participate in the same Spring transaction. JmsTemplate automatically participates in the JMS resource bound to the thread.

### XA/JTA

Use it when you need a unified commit/rollback result between JMS and another resource, for example a database, and all resource managers support XA.

Example of configuring a listener container with a transaction manager:

~~~java
factory.setTransactionManager(jtaTransactionManager);
~~~

In the XA case, the ConnectionFactory must be XA-capable and properly registered with the transaction coordinator. Merely creating a JtaTransactionManager is not enough.

When a Session participates in a JTA transaction managed by an application server, the application does not call Session.commit() or Session.rollback() itself. The transaction coordinator decides the final outcome.

## 10. A Complete Example: Commit, Rollback, and Redelivery

This example uses Java 17, Jakarta Messaging 3.1, and the Apache ActiveMQ Artemis Jakarta client 2.40.0. The program connects to a running Artemis broker, creates two separate transacted Sessions, and then observes three scenarios:

1. The producer sends a message and commits.
2. The consumer receives the message and rolls back, then receives the message again with JMSRedelivered=true and commits.
3. The producer sends a message and then rolls back; the consumer does not receive that message.

Project structure:

~~~text
local-jms-transaction-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── LocalSessionTransactionDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>local-jms-transaction-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.40.0</version>
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

### src/main/java/demo/LocalSessionTransactionDemo.java

~~~java
package demo;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public class LocalSessionTransactionDemo {

    public static void main(String[] args) throws Exception {
        String brokerUrl = System.getenv().getOrDefault(
                "JMS_BROKER_URL", "tcp://localhost:61616");

        ConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory(brokerUrl);

        try (Connection connection = connectionFactory.createConnection()) {
            Session producerSession =
                    connection.createSession(true, Session.SESSION_TRANSACTED);
            Session consumerSession =
                    connection.createSession(true, Session.SESSION_TRANSACTED);

            try {
                Queue producerQueue =
                        producerSession.createQueue("orders.local.tx.demo");
                Queue consumerQueue =
                        consumerSession.createQueue("orders.local.tx.demo");

                MessageProducer producer =
                        producerSession.createProducer(producerQueue);
                MessageConsumer consumer =
                        consumerSession.createConsumer(consumerQueue);

                try {
                    connection.start();

                    producer.send(
                            producerSession.createTextMessage("Order #1024"));
                    producerSession.commit();
                    System.out.println("[send] committed: Order #1024");

                    Message first = consumer.receive(5000);
                    if (!(first instanceof TextMessage firstText)) {
                        throw new IllegalStateException(
                                "Expected the first order message");
                    }

                    System.out.println(
                            "[receive] first delivery: " + firstText.getText());

                    consumerSession.rollback();
                    System.out.println("[transaction] receive rollback");

                    Message second = consumer.receive(5000);
                    if (!(second instanceof TextMessage secondText)) {
                        throw new IllegalStateException(
                                "Expected the rolled-back message again");
                    }

                    System.out.println(
                            "[receive] redelivered: " + secondText.getText());
                    System.out.println(
                            "[receive] JMSRedelivered: "
                                    + second.getJMSRedelivered());

                    consumerSession.commit();
                    System.out.println("[transaction] receive commit");

                    producer.send(
                            producerSession.createTextMessage("Order #discard"));
                    producerSession.rollback();
                    System.out.println(
                            "[send] rolled back: Order #discard");

                    Message discarded = consumer.receive(500);
                    if (discarded != null) {
                        throw new IllegalStateException(
                                "A rolled-back send must not be delivered");
                    }

                    System.out.println(
                            "[receive] after send rollback: none");
                }
                finally {
                    consumer.close();
                    producer.close();
                }
            }
            finally {
                consumerSession.close();
                producerSession.close();
            }
        }
    }
}
~~~

Run in the directory containing pom.xml:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.LocalSessionTransactionDemo
~~~

The broker is looked up by default at tcp://localhost:61616. The queue orders.local.tx.demo must exist or the broker must allow automatic queue creation. If the broker uses a different address, set the environment variable JMS_BROKER_URL before running.

Expected output when the broker accepts the connection and supports queues:

~~~text
[send] committed: Order #1024
[receive] first delivery: Order #1024
[transaction] receive rollback
[receive] redelivered: Order #1024
[receive] JMSRedelivered: true
[transaction] receive commit
[send] rolled back: Order #discard
[receive] after send rollback: none
~~~

### Analysis of the Example

**Two independent Sessions:** producerSession and consumerSession are both transacted. They use the same Connection and destination, but each Session has its own transaction.

**Producer-side commit:** the producer sends Order #1024 and then calls producerSession.commit(). The message is committed and can be received by the consumer.

**Consumer-side rollback:** the consumer receives the message in consumerSession and then rolls back. The broker redelivers the message; the JMSRedelivered header of the next receive is true.

**Consumer-side commit:** the consumer receives the message again and commits. The message is acknowledged in the receiving transaction.

**Producer-side rollback:** the producer sends Order #discard but rolls back before committing. The sent message is discarded and the consumer does not receive it.

The example demonstrates the transaction scope of each Session. The producerSession commit does not commit the consumerSession; each Session has an independent boundary.

This is an integration example with a real broker, not a mock. If you only run compile without a broker, the program may compile but cannot confirm actual redelivery or transaction behavior.

## 11. Broker Configuration for Redelivery and Dead-Letter

A rollback makes the message eligible for redelivery. If a listener always fails on the same message, the broker may redeliver continuously and create an error loop.

In a real environment, configure a redelivery policy:

- Maximum number of redeliveries.
- Delay between attempts.
- Increasing backoff if the provider supports it.
- A dead-letter address/queue after the limit is exceeded.
- Monitoring of message age and redelivery count.

JMS has the JMSRedelivered property to indicate that a message was delivered before and is being delivered again. Some providers also supply JMSXDeliveryCount to know the number of deliveries.

Do not use the redelivery count as the sole idempotency key. Use a stable event ID or business operation ID to identify the business operation.

## 12. Transactions and Message Durability Are Two Different Concepts

A Session transaction decides whether a group of send/receive operations is committed or rolled back. The delivery mode decides whether the provider stores the message durably across failures.

| Concept | Question it addresses |
|---|---|
| Session transaction | Do the send/receive operations in the group complete together? |
| PERSISTENT delivery mode | Does the provider store the message durably according to its policy? |
| Durable Topic subscription | Does the subscription continue to exist when there is no consumer? |
| Acknowledgment | When does the provider consider the received message acknowledged? |

A message sent in a committed transaction but using NON_PERSISTENT still does not have the same storage guarantee as a PERSISTENT message when the provider fails.

Conversely, PERSISTENT does not replace a transaction. If a transaction is rolled back, a message sent in the transaction is still discarded under the transaction rules.

## 13. Common Mistakes

**Forgetting to commit:** a message sent in a transacted Session has not been committed. When the Session closes, the open transaction is rolled back.

**Calling rollback after a commit:** the commit already ended the earlier transaction. A rollback afterwards applies to a new transaction if there is one; it cannot undo a commit that has completed.

**Using commit() on a non-transacted Session:** this operation is invalid and may raise an IllegalStateException.

**Thinking all Sessions on the same Connection share one transaction:** each Session has its own transaction. Committing one Session has no effect on another Session.

**Using CLIENT_ACKNOWLEDGE together with SESSION_TRANSACTED:** the two modes are mutually exclusive. With a transacted Session, commit/rollback control acknowledgment and recovery.

**Swallowing the exception and letting the listener complete:** the container may commit the message even though the business operation failed. Let an appropriate exception propagate out of the listener or deliberately roll back by design.

**Assuming rollback always yields exactly-once:** a rollback can cause the message to be redelivered. The listener must be idempotent to avoid repeated effects.

**Assuming a JMS transaction includes the database:** a local JMS transaction only manages the Session. Use XA/JTA or an outbox/inbox when you need to coordinate multiple resources.

**Using JmsTransactionManager as the transaction manager for all resources:** JmsTransactionManager manages one JMS ConnectionFactory. It does not replace the database's transaction manager.

**Calling Session.commit() inside a JTA transaction:** when the Session is managed by the container/JTA, the transaction coordinator is responsible for commit/rollback. Do not manage the Session yourself as a local transaction.

**Enabling sessionTransacted without configuring redelivery:** the broker still needs a redelivery and dead-letter policy to avoid a poison message repeating indefinitely.

**Confusing PERSISTENT with transacted:** the delivery mode and the transaction are two independent mechanisms.

## 14. Best Practices

1. Use a transacted Session when you need to group receiving and sending messages in the same JMS transaction.
2. Commit after the business operation within the JMS scope completes.
3. Roll back when processing fails and you want the broker to redeliver the message.
4. Do not share a Session among multiple threads.
5. Use JmsTransactionManager when multiple JmsTemplate operations need the same local transaction.
6. Use sessionTransacted=true on the listener container when you need a rollback if the listener fails.
7. Set a redelivery limit and a dead-letter policy on the broker.
8. Design idempotent listeners because messages may be redelivered.
9. Keep the JMS transaction and the database transaction clearly separate.
10. Choose XA/JTA when you truly need atomic commit across multiple XA resources.
11. Consider an outbox/inbox when you want to reduce the complexity of distributed transactions.
12. Monitor transaction rollbacks, redelivery count, message age, dead-letter volume, and commit errors.

## 15. Takeaways

- sessionTransacted creates a local transaction on one JMS Session.
- commit() acknowledges received messages and completes sent messages in the same Session.
- rollback() undoes sent messages and makes received messages eligible for redelivery.
- Different Sessions have independent transactions, even when they use the same Connection.
- In a transacted Session, the acknowledgment mode is managed by commit/rollback.
- JmsTemplate can use a transacted Session via setSessionTransacted(true).
- JmsTransactionManager manages a local transaction for one ConnectionFactory and binds the Session to the thread.
- A listener container with sessionTransacted=true commits when the listener succeeds and rolls back when the listener throws an exception.
- A local JMS transaction does not automatically include the database or HTTP.
- XA/JTA needs XA-capable resources and a transaction coordinator; outbox/inbox is an alternative for many architectures.
- A rollback can lead to redelivery; you need idempotency and a dead-letter policy.
- A transaction and the persistent delivery mode solve two different problems.

## References

- [Spring Framework 6.2 — Using Spring JMS: Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Receiving a Message: Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2 — JmsTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [Spring Framework 6.2 — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Jakarta Messaging 3.1 Specification — Transactions and message acknowledgment](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta Messaging 3.1 — Session API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session)
