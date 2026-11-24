# Receiving and Sending a Reply in the Same JMS Transaction with Spring

In a JMS request-reply flow, the listener receives a request, processes the data, and then sends a response to the destination that the request specifies. If the request has been acknowledged but the response has not been sent successfully, the caller may never receive the result even though the business operation has run. Spring JMS solves this problem by letting the listener container perform the receive and the response send in the same JMS transaction.

With a local JMS transaction, the core condition is that **receiving the request and sending the response must use the same transacted JMS Session**. When the listener completes normally, the container commits the session: the request is acknowledged and the response is sent. If the listener or the response send fails, the container rolls back: the request is redelivered and the response already sent in that session is also rolled back.

## 1. Why Do You Need a Transaction for Both Receive and Reply?

Suppose a producer sends a request to the `orders` queue and asks for a reply via `JMSReplyTo=order-replies`.

A flow without a transaction can run into this situation:

1. The listener receives the request.
2. The provider acknowledges the request.
3. The listener creates the response but sending the response fails.
4. The request has already been acknowledged so it is not redelivered.
5. The caller waits for a response but never receives it.

If the listener uses one transacted session for both the receive and the reply, the provider handles the two operations in the same transaction:

- Commit: the request is acknowledged and the response becomes available.
- Rollback: the request returns to the queue to be processed again; the uncommitted response does not appear in the reply queue.

This is how you keep consistency between consuming the request and emitting the response within the scope of one JMS resource.

## 2. Enabling a Local JMS Transaction with sessionTransacted

With `DefaultMessageListenerContainer`, enable:

```java
container.setSessionTransacted(true);
```

Each listener invocation runs in a JMS Session with a transaction. The container is responsible for committing when the listener completes successfully and rolling back when the listener throws an exception.

Configuration example:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setConnectionFactory(connectionFactory);
container.setDestinationName("orders");
container.setMessageListener(orderListener);
container.setSessionTransacted(true);
container.setConcurrency("2-8");
```

When the local transaction is enabled:

- The listener does not need to call `session.commit()` or `session.rollback()` itself.
- Do not close the Session supplied by the container.
- If processing fails, let the exception escape the listener so that the container notices and rolls back.
- If you catch the exception and return normally, the container may interpret the listener as successful and commit the request together with the response.

Each listener invoker has its own session. When you increase concurrency, each processing pass still has an independent transaction on the corresponding session.

### Commit and Rollback Flow

```text
Receive request on a transacted Session
                 |
                 v
          Business processing
                 |
                 v
           Send response
                 |
           Listener ends
             /       \
            /         \
        Success      Exception
            |               |
            v               v
         COMMIT           ROLLBACK
            |               |
            v               v
    Ack request +       Redeliver request
    publish response    + discard uncommitted response
```

The transaction only covers operations participating in the same JMS Session. Independent database or HTTP operations are not automatically inside this transaction.

## 3. Using SessionAwareMessageListener to Send the Response with the Same Session

`SessionAwareMessageListener` is a Spring-specific interface. It extends the capability of the JMS `MessageListener` by passing the very `Session` that received the message into the callback:

```java
public interface SessionAwareMessageListener<M extends jakarta.jms.Message> {
    void onMessage(M message, jakarta.jms.Session session)
            throws jakarta.jms.JMSException;
}
```

This is the explicit way to send the response in the same local transaction:

```java
import jakarta.jms.Destination;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.jms.listener.SessionAwareMessageListener;

public class OrderListener
        implements SessionAwareMessageListener<TextMessage> {

    @Override
    public void onMessage(TextMessage request, Session session)
            throws jakarta.jms.JMSException {

        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            throw new IllegalStateException("Request has no JMSReplyTo");
        }

        String orderId = request.getText();
        String result = "accepted:" + orderId;

        TextMessage response = session.createTextMessage(result);
        response.setJMSCorrelationID(request.getJMSCorrelationID());

        try (MessageProducer producer = session.createProducer(replyTo)) {
            producer.send(response);
        }
    }
}
```

The container passes the Session in use for receiving the request. The producer is created from that session, so the response send participates in the same local JMS transaction.

You can close the `MessageProducer` after sending; do not close the Session or Connection because the container manages their lifecycle.

If `producer.send(response)` throws an exception, the exception escapes the callback and the container rolls back the session. The request is redelivered by the provider according to the broker's policy.

## 4. Using @JmsListener and @SendTo

With annotated endpoints, Spring can send the response automatically from the method's return value. Configure the listener container factory with `sessionTransacted=true`:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");

        return factory;
    }
}
```

Enable annotation listeners with `@EnableJms`, then declare the endpoint:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
public class OrderEndpoint {

    @JmsListener(destination = "orders")
    @SendTo("order-replies")
    public OrderReply processOrder(OrderRequest request) {
        // Validate and process the request.
        return new OrderReply(request.orderId(), "ACCEPTED");
    }
}
```

Spring converts the return value into a JMS message and sends it to the response destination. With a transacted listener container configuration, receiving the request, invoking the method, and sending the response all fall within the processing lifecycle of the listener session.

Some response routing rules:

- `JMSReplyTo` on the request specifies the reply destination specific to that request.
- `@SendTo` determines the default response destination for the endpoint.
- If you need to choose the destination based on the request data, you can return a `JmsResponse` with a destination.
- A method that returns `void` or a `null` value does not create an automatic response.

If you need to create JMS headers yourself, you can return a Spring `Message<T>` instead of a plain payload. If you need to use the native JMS API, a `@JmsListener` method can also accept the parameters `jakarta.jms.Session` and `jakarta.jms.Message`:

```java
@JmsListener(destination = "orders")
public void process(TextMessage request, Session session)
        throws JMSException {
    Destination replyTo = request.getJMSReplyTo();
    // Create and send response with this session.
}
```

When using this approach, send the response with the injected Session to ensure it belongs to the same local JMS transaction.

## 5. MessageListenerAdapter Also Supports Automatic Responses

`MessageListenerAdapter` lets you turn a POJO into a message-driven listener. If the handling method returns a value other than `void`, the adapter can convert the result into a JMS message and send the response.

Example delegate method:

```java
public class OrderDelegate {

    public String handleMessage(String orderId) {
        return "accepted:" + orderId;
    }
}
```

Configure the adapter and the default destination:

```java
MessageListenerAdapter adapter =
        new MessageListenerAdapter(new OrderDelegate());

adapter.setDefaultResponseDestination(orderReplyQueue);
```

The adapter sends the response to the destination in the request's `JMSReplyTo` header if present; otherwise, it uses the configured default response destination. If no suitable destination is found, the response send fails and the exception may be propagated back to the listener container.

For the receive and the response to be in the same local transaction, set the adapter as the listener of a container with `sessionTransacted=true`. The container invokes the adapter in the listener session's transaction.

## 6. Correlation ID and Reply Destination

Request-reply needs a way to match a response with its corresponding request, especially when many requests are waiting at the same time.

### JMSReplyTo

`JMSReplyTo` is a header holding the destination to which the caller wants to receive the response. A request can use a dedicated reply queue, a shared queue, or a temporary queue.

Example:

```java
client.send("orders", session -> {
    TextMessage request = session.createTextMessage("order-42");
    request.setJMSReplyTo(session.createQueue("order-replies"));
    request.setJMSCorrelationID("corr-42");
    return request;
});
```

If the listener cannot find a reply destination and there is no default destination such as `@SendTo`, creating the response will fail.

A temporary queue is useful for short-lived request-reply because the caller creates a queue to receive the response and then closes it when no longer needed. However, the caller must keep the connection/destination alive during the wait and ensure the provider allows the listener to send to that temporary destination.

### JMSCorrelationID

`JMSCorrelationID` helps the caller match a response with a request. There are two commonly used conventions:

- The caller sets its own correlation ID on the request; the listener copies that value into the response.
- The caller does not set a correlation ID; the listener uses the request's `JMSMessageID` as the correlation ID on the response.

Example:

```java
response.setJMSCorrelationID(request.getJMSCorrelationID());
```

Do not rely on the order in which responses are received to match requests when there are many concurrent requests. Use a correlation ID and check it on the caller side.

## 7. Local JMS Transaction and JTA/XA

### Local JMS Transaction

`sessionTransacted=true` creates a local transaction on the JMS Session. It is suitable when you need atomicity among:

- Receiving a request from a queue/topic subscription.
- Sending one or more responses with the same session.
- Other JMS operations on the same session.

A local JMS transaction does not automatically include the database, the filesystem, or an HTTP service.

For example, the listener updates the database successfully and then sending the response fails: the database may have committed while the JMS session rolls back. The request is redelivered and the database operation may run again. Design idempotency or duplicate detection to avoid writing the data twice.

### External Transaction and XA

If you need to receive a request, update the database, and send a response in a single distributed transaction, you need a transaction manager and resources that support XA.

With Spring, configure a `JtaTransactionManager` for the listener container and use a JMS `ConnectionFactory` with XA registered with the transaction coordinator:

```java
factory.setConnectionFactory(xaConnectionFactory);
factory.setTransactionManager(jtaTransactionManager);
```

The database must also participate in XA if it needs to commit together with JMS. In that case the transaction coordinator decides to commit or roll back the enlisted resources.

XA provides atomicity across resources but increases cost and operational complexity, including the transaction log, recovery, and provider configuration. Use it only when the consistency requirement truly needs an atomic commit across multiple resources.

### JmsTransactionManager

`JmsTransactionManager` manages a local transaction for one JMS `ConnectionFactory`. It can bind the Connection/Session to the thread so that appropriate Spring JMS operations participate in the same transaction. It does not turn an independent database transaction into an XA transaction.

When the listener needs to send a response, the most controllable approach is to use the Session the container passes in. If you use `JmsTemplate` inside the listener, you need to determine clearly whether the template participates in the same active transaction manager/resource; an independent Session does not automatically belong to the listener's transaction.

## 8. What Happens When the Listener or the Response Send Fails?

With a local transacted session, an error before the commit leads to a rollback:

| Failure moment | Result |
| --- | --- |
| Request validation fails | The request is rolled back and may be redelivered |
| Business processing throws an exception | The request is rolled back |
| Sending the response throws an exception | The request is rolled back; the uncommitted response is dropped from the transaction |
| The response is sent successfully, then the listener throws an exception | Both the receive and the reply are rolled back |
| The listener ends normally | The request and the response commit in the same transaction |

For the transaction to roll back, the error must be propagated to the container. If the listener catches the exception, ignores it, and ends normally, the container may commit. For an error that needs a rollback but that you do not want to throw out, you need to mark the transaction rollback-only through an appropriate transaction manager mechanism.

### Redelivery and Poison Messages

A rollback lets the provider redeliver the request. JMS sets the `JMSRedelivered` flag when a message is redelivered; many providers also supply the `JMSXDeliveryCount` property.

Redelivery can repeat many times if the error always occurs. Configure:

- Maximum number of redeliveries.
- Pause or backoff between retries.
- A dead-letter queue for messages that exceeded the number of attempts.
- Logging with the request ID, correlation ID, and delivery count.
- Idempotency to handle safely when the request is redelivered.

Do not retry indefinitely on unrecoverable data errors. A message with the wrong schema or missing required fields should be moved to an error/DLQ flow according to the broker's policy.

## 9. Java 17+ Example: Verifying Rollback of Both Request and Response with Artemis

The following example uses embedded ActiveMQ Artemis and Spring JMS. The listener sends the response using the very Session that the container supplies, and then deliberately throws an exception on the first processing pass. The broker rolls back both the request and the response. The request is redelivered; the second processing pass succeeds and the caller receives only one response.

Create the file `src/main/java/TransactionalJmsReplyDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.jms.Destination;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.apache.activemq.artemis.api.core.QueueConfiguration;
import org.apache.activemq.artemis.api.core.RoutingType;
import org.apache.activemq.artemis.core.config.impl.ConfigurationImpl;
import org.apache.activemq.artemis.core.server.embedded.EmbeddedActiveMQ;
import org.apache.activemq.artemis.core.remoting.impl.invm.InVMConnector;
import org.apache.activemq.artemis.core.remoting.impl.invm.InVMRegistry;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.SessionAwareMessageListener;

public class TransactionalJmsReplyDemo {

    public static void main(String[] args) throws Exception {
        EmbeddedActiveMQ broker = new EmbeddedActiveMQ();
        ActiveMQConnectionFactory connectionFactory = null;
        DefaultMessageListenerContainer container = null;

        try {
            ConfigurationImpl configuration = new ConfigurationImpl()
                    .setPersistenceEnabled(false)
                    .setSecurityEnabled(false)
                    .setJMXManagementEnabled(false)
                    .addAcceptorConfiguration("invm", "vm://0");

            broker.setConfiguration(configuration).start();

            broker.getActiveMQServer().createQueue(
                    QueueConfiguration.of("requests")
                            .setAddress("requests")
                            .setRoutingType(RoutingType.ANYCAST)
                            .setDurable(false));

            broker.getActiveMQServer().createQueue(
                    QueueConfiguration.of("replies")
                            .setAddress("replies")
                            .setRoutingType(RoutingType.ANYCAST)
                            .setDurable(false));

            connectionFactory = new ActiveMQConnectionFactory("vm://0");

            JmsTemplate client = new JmsTemplate(connectionFactory);
            client.setReceiveTimeout(5_000);

            AtomicInteger attempts = new AtomicInteger();

            SessionAwareMessageListener<TextMessage> listener =
                    (request, session) -> {
                int attempt = attempts.incrementAndGet();

                System.out.println("listener attempt=" + attempt
                        + ", redelivered=" + request.getJMSRedelivered());

                Destination replyTo = request.getJMSReplyTo();
                if (replyTo == null) {
                    throw new IllegalStateException("Request has no JMSReplyTo");
                }

                TextMessage response = session.createTextMessage(
                        "processed:" + request.getText());

                response.setJMSCorrelationID(
                        request.getJMSCorrelationID());

                try (MessageProducer producer =
                             session.createProducer(replyTo)) {
                    producer.send(response);
                }

                // First attempt sends a reply, then forces the whole session to roll back.
                if (attempt == 1) {
                    throw new IllegalStateException(
                            "Simulated failure after reply send");
                }
            };

            container = new DefaultMessageListenerContainer();
            container.setConnectionFactory(connectionFactory);
            container.setDestinationName("requests");
            container.setMessageListener(listener);
            container.setSessionTransacted(true);
            container.setCacheLevel(
                    DefaultMessageListenerContainer.CACHE_CONSUMER);
            container.setRecoveryInterval(200);
            container.afterPropertiesSet();
            container.start();

            client.send("requests", session -> {
                TextMessage request = session.createTextMessage("order-42");
                request.setJMSReplyTo(session.createQueue("replies"));
                request.setJMSCorrelationID("corr-42");
                return request;
            });

            Message reply = client.receive("replies");
            if (!(reply instanceof TextMessage textReply)) {
                throw new IllegalStateException("No text reply received");
            }

            client.setReceiveTimeout(300);
            Message duplicateReply = client.receive("replies");

            System.out.println("reply payload=" + textReply.getText());
            System.out.println("reply correlationId="
                    + textReply.getJMSCorrelationID());
            System.out.println("listener attempts=" + attempts.get());
            System.out.println("duplicate reply absent="
                    + (duplicateReply == null));

            if (attempts.get() != 2 || duplicateReply != null) {
                throw new IllegalStateException(
                        "Unexpected transactional reply behavior");
            }
        }
        finally {
            if (container != null) {
                container.stop();
                container.destroy();
            }

            if (connectionFactory != null) {
                connectionFactory.close();
            }

            broker.stop();

            // Clean up the embedded Artemis in-VM transport threads.
            InVMRegistry.instance.clear();
            InVMConnector.resetThreadPool();
        }
    }
}
```

Create `pom.xml` in the root directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>transactional-jms-reply-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>7.0.10</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.10</version>
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
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>TransactionalJmsReplyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Run from the directory containing `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Stdout result:

```text
listener attempt=1, redelivered=false
listener attempt=2, redelivered=true
reply payload=processed:order-42
reply correlationId=corr-42
listener attempts=2
duplicate reply absent=true
```

On the first pass the listener sent the response but then threw an exception. Because the response was sent with the same transacted Session, the broker rolled back both the response and the request receive operation. The broker redelivered the request; on the second pass the listener completed normally, so the request was acknowledged and only one response was committed.

The example uses an embedded Artemis with persistence turned off to test the transaction behavior. It does not need an external broker; for production deployment, replace the embedded broker with the ConnectionFactory of the provider you use.

## 10. Limitations to Remember

### Request and Reply Are Not One End-to-End Transaction Across the Caller

The transaction at the listener protects the receive of the request and the send of the response on the server side. The caller sending the request and the caller receiving the response usually happen in different sessions/transactions. If the caller sends the request successfully but times out waiting for the reply, the server may still have processed it and committed the response.

The caller needs a timeout, a correlation ID, and an appropriate retry policy. Do not assume a timeout means the request was not processed.

### A JMS Transaction Does Not Automatically Include the Database

If the listener writes to the database and then sends the response, the local JMS transaction only rolls back the JMS operations. The database may have already committed. Use an idempotency key, inbox/deduplication, or a transactional outbox depending on the architecture.

If the database update, the request acknowledgement, and the reply send must commit atomically, you need JTA/XA with all resources configured and enlisted correctly.

### AUTO_ACKNOWLEDGE Does Not Replace a Transacted Session

The default acknowledgement mode does not guarantee a rollback of the receive together with the send. For reliability requirements, enable `sessionTransacted=true` or use an appropriate transaction manager.

`CLIENT_ACKNOWLEDGE` also does not make the response send part of the receive transaction. To get an atomic receive/reply, use the same transacted Session.

### Do Not Let a Response Go Missing for Lack of a Destination

If the request has no `JMSReplyTo`, the listener must have a default response destination such as `@SendTo` or `MessageListenerAdapter.setDefaultResponseDestination`. If there is no destination, Spring cannot send the response and the listener will fail.

### Do Not Use a Session Concurrently Across Multiple Threads

A JMS Session is not thread-safe. Create the response with the Session passed into the callback and send it in the same processing thread. Do not store the Session in a field or hand it to another executor.

## 11. Common Mistakes

1. **Enabling the listener but forgetting `sessionTransacted=true`.** The listener may receive the request and send the response without an atomic rollback.
2. **Sending the response with an independent Session.** The response may commit even though the request rolls back, creating a duplicate response when the request is redelivered.
3. **Using `JmsTemplate` and thinking it automatically uses the listener's Session.** A template may obtain a different Session; use the injected Session or configure a transaction manager to share the resource correctly.
4. **Catching the exception and ignoring it.** The container sees the listener end normally and may commit the request.
5. **Using `CLIENT_ACKNOWLEDGE` instead of a transacted session.** Acknowledge does not group the response send operation into the same transaction.
6. **Not setting `JMSReplyTo` or a default destination.** The adapter has nowhere to send the response.
7. **Not setting a correlation ID.** The caller has difficulty matching responses when there are many concurrent requests.
8. **Not handling redelivery.** A request may be executed multiple times after a rollback or a connection error.
9. **Retrying data-error messages indefinitely.** A poison message can loop continuously; you need a retry limit and a DLQ.
10. **Assuming a local JMS transaction includes the database.** It only includes the JMS operations on the corresponding resource/session.
11. **Using XA when the ConnectionFactory does not support XA.** JTA cannot enlist a JMS resource without XA capability.
12. **Letting the listener run for a long time in request-reply.** The caller holds resources during the wait; long-running work should use a command + job ID/status event.

## 12. Implementation Checklist

- Choose `DefaultMessageListenerContainer` or a listener factory that supports transactions.
- Enable `sessionTransacted=true` if the receive and the reply must be atomic on one JMS resource.
- Send the reply through the same Session the container passes in, or use Spring's reply adapter mechanism.
- Choose the destination from `JMSReplyTo`, `@SendTo`, or the default response destination.
- Set the correlation ID and check it at the caller.
- Let the exception escape the listener when a rollback is needed.
- Configure redelivery, the retry limit, and a dead-letter queue.
- Make the listener idempotent to handle a redelivered request safely.
- Use JTA/XA if you need an atomic commit between JMS and the database/another resource.
- Test the failure scenario after sending the response but before the listener completes.
- Monitor redelivery count, rollbacks, reply timeouts, and messages entering the DLQ.

## 13. References

- [Spring Framework – Receiving a Message: Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework – SessionAwareMessageListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/SessionAwareMessageListener.html)
- [Spring Framework – DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework – Annotation-driven Listener Endpoints and @SendTo](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework – MessageListenerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/adapter/MessageListenerAdapter.html)
- [Spring Framework – JmsTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html)
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.pdf)
