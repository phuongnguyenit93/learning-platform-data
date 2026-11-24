# SessionCallback, ProducerCallback, and Advanced JMS Operations

Spring JMS provides **JmsTemplate** so applications can send and receive messages without repeatedly creating and releasing Connection, Session, MessageProducer, and MessageConsumer manually. For standard operations, methods such as send, convertAndSend, receive, and sendAndReceive are usually sufficient.

When deeper control over the Jakarta Messaging API is required, JmsTemplate provides two key callbacks:

- **SessionCallback<T>** lets you perform one or more operations on a JMS Session provided by the template.
- **ProducerCallback<T>** lets you work simultaneously with a JMS Session and a MessageProducer created by the template.

Both callbacks fit when a business operation requires multiple JMS steps in a single call, per-message Quality of Service (QoS) settings, specialized Session APIs, or custom request/reply flows.

## 1. How Does JmsTemplate Manage Resources?

A basic JMS sending flow typically requires these objects:

~~~text
ConnectionFactory
      |
      v
Connection
      |
      v
Session
      |
      v
MessageProducer
      |
      v
Destination
~~~

If calling the Jakarta Messaging API directly everywhere, the application must manage creating and closing intermediate objects, translating JMSException, configuring transactions, and ensuring resources are not reused past their valid lifecycle.

JmsTemplate centralizes this infrastructure into a shared template. The application passes a callback to perform the required business work. When the callback completes or throws an exception, the template releases the resources it created and owns.

**JmsTemplate is thread-safe once configured.** A single shared instance can be used across multiple services. However, Session, MessageProducer, and MessageConsumer are resources tied to a single execution; do not store them in shared fields or share them across threads.

### Comparing the callbacks

| Callback | Provided Objects | When to Use |
|---|---|---|
| **MessageCreator** | Session | Only need to create a single message to send via standard send methods. |
| **SessionCallback<T>** | Session | Need multiple JMS operations on the same Session, create consumers, temporary destinations, or call Session APIs directly. |
| **ProducerCallback<T>** | Session and MessageProducer | Need to send multiple messages through the same producer or adjust QoS on each send. |
| **BrowserCallback<T>** | Session and QueueBrowser | Need to browse messages in a queue without consuming them from the queue. |
| **MessagePostProcessor** | Message after converter creation | Need to add properties or JMS headers after convertAndSend. |

Both SessionCallback and ProducerCallback return a type T chosen by the application. They can return the number of messages sent, query results, a received message, or null if no result is needed.

## 2. SessionCallback<T>: Working Directly with Session

The **org.springframework.jms.core.SessionCallback<T>** interface has a single method:

~~~java
T doInJms(Session session) throws JMSException;
~~~

JmsTemplate invokes this method with a Session prepared according to the ConnectionFactory configuration and active transaction. After the callback finishes, the template manages the lifecycle of the Session and Connection it owns.

Callback invocation example:

~~~java
Integer result = jmsTemplate.execute(session -> {
    TextMessage message = session.createTextMessage("Order created");
    message.setStringProperty("eventType", "OrderCreated");
    return message.getText().length();
});
~~~

This snippet illustrates using Session to create a message and return a result. If you only need to send a single message, MessageCreator or jmsTemplate.send(...) is usually more concise. SessionCallback shines when coordinating multiple JMS operations within one callback.

### Operations commonly needing SessionCallback

- Creating a Message of a specific JMS type such as TextMessage, BytesMessage, or MapMessage.
- Creating MessageProducers or MessageConsumers for multiple destinations.
- Creating a TemporaryQueue or TemporaryTopic to implement a custom request/reply protocol.
- Creating a consumer with a selector or noLocal setting.
- Accessing Session APIs not exposed by higher-level convenience methods.
- Combining multiple operations on the same Session when an appropriate transaction boundary is needed.

### Example: request/reply with a temporary queue

JmsTemplate includes sendAndReceive(...) to send a request and wait for a reply on a template-created temporary queue. Only write it manually with SessionCallback when finer protocol control is needed, such as managing temporary destinations, selectors, or multiple send/receive steps yourself.

The example below assumes a receiving service reads JMSReplyTo, processes the request, and sends a TextMessage reply to that destination. The callback creates a temporary queue, registers the consumer before sending the request, waits up to three seconds, and cleans up the resources created by the callback itself.

~~~java
public String requestReply(Destination requestDestination, String body) {
    return jmsTemplate.execute(session -> {
        TemporaryQueue replyQueue = session.createTemporaryQueue();
        MessageProducer producer = null;
        MessageConsumer consumer = null;

        try {
            producer = session.createProducer(requestDestination);
            consumer = session.createConsumer(replyQueue);

            String correlationId = UUID.randomUUID().toString();

            TextMessage request = session.createTextMessage(body);
            request.setJMSReplyTo(replyQueue);
            request.setJMSCorrelationID(correlationId);

            producer.send(request);

            Message reply = consumer.receive(3_000L);
            if (reply == null) {
                return null;
            }

            if (!(reply instanceof TextMessage textReply)) {
                throw new JMSException("Expected a TextMessage reply");
            }

            if (!correlationId.equals(reply.getJMSCorrelationID())) {
                throw new JMSException("Reply correlation ID does not match");
            }

            return textReply.getText();
        }
        finally {
            try {
                if (consumer != null) {
                    consumer.close();
                }
            }
            finally {
                try {
                    if (producer != null) {
                        producer.close();
                    }
                }
                finally {
                    replyQueue.delete();
                }
            }
        }
    }, true);
}
~~~

The true parameter instructs JmsTemplate to start the Connection before the callback performs receive operations. This is essential so the consumer can receive messages from the provider. The callback closes the producer, consumer, and temporary queue it created; the template manages its Session and Connection.

Request/reply only completes if the receiving service actually sends a reply to JMSReplyTo and preserves JMSCorrelationID. If three seconds elapse with no reply, the method returns null. In real systems, handle timeouts, late replies, and errors from the receiving service.

## 3. ProducerCallback<T>: Working with Session and MessageProducer

The **org.springframework.jms.core.ProducerCallback<T>** interface has the method:

~~~java
T doInJms(Session session, MessageProducer producer)
        throws JMSException;
~~~

ProducerCallback fits when sending multiple messages in one call or using JMS send overloads to specify QoS per message.

JmsTemplate provides the overloads:

~~~java
jmsTemplate.execute(destination, producerCallback);
jmsTemplate.execute(destinationName, producerCallback);
jmsTemplate.execute(producerCallback); // requires default destination
~~~

When a destination is passed, the template creates a producer bound to that destination, invokes the callback, and then closes the producer it created. Do not manually close the producer passed into the callback.

### Example: sending a batch with explicit QoS

~~~java
public int sendBatch(Destination destination, List<String> payloads) {
    return jmsTemplate.execute(destination, (session, producer) -> {
        for (int i = 0; i < payloads.size(); i++) {
            TextMessage message = session.createTextMessage(payloads.get(i));
            message.setIntProperty("batchIndex", i);
            message.setStringProperty("eventType", "OrderEvent");

            producer.send(
                    message,
                    DeliveryMode.PERSISTENT,
                    4,
                    60_000L
            );
        }

        return payloads.size();
    });
}
~~~

Each message is sent with:

- **DeliveryMode.PERSISTENT:** asks the provider to store the message using persistent delivery mode.
- **priority = 4:** JMS priority level between 0 and 9; higher numbers indicate higher priority.
- **timeToLive = 60_000L:** 60-second time to live in milliseconds.

The return value is the number of messages sent by the callback. If one send throws JMSException, the callback stops and JmsTemplate translates the error into Spring JMS's unchecked exception hierarchy. Whether earlier messages are kept or rolled back depends on the session transaction and provider.

### When to choose ProducerCallback over standard send?

Use send(...) or convertAndSend(...) when sending a single message with shared settings. Choose ProducerCallback when:

- One call needs to send multiple messages to the same destination.
- Each message needs its own delivery mode, priority, or time-to-live.
- Direct MessageProducer API access is needed.
- Multiple JMS Message types need to be created and sent from the same Session.
- You want to reduce producer creation count for a batch send.

ProducerCallback supplies only a single producer. If you need to send to multiple destinations within the same Session, consider SessionCallback and create the needed producers yourself, then close them in the callback.

## 4. QoS: Delivery Mode, Priority, and Time-to-Live

JMS defines important QoS parameters for send operations:

| Property | Meaning | Common Values |
|---|---|---|
| Delivery mode | Requests persistent or non-persistent delivery. | **DeliveryMode.PERSISTENT**, **DeliveryMode.NON_PERSISTENT**. |
| Priority | Message priority level. | 0 to 9; default is usually 4. |
| Time-to-live | How long a message remains valid before expiring. | Milliseconds; 0 means no expiration limit. |

### Shared QoS configuration on JmsTemplate

You can configure default QoS for the template's send operations:

~~~java
jmsTemplate.setDeliveryMode(DeliveryMode.PERSISTENT);
jmsTemplate.setPriority(4);
jmsTemplate.setTimeToLive(60_000L);
jmsTemplate.setExplicitQosEnabled(true);
~~~

explicitQosEnabled must be turned on so JmsTemplate applies the delivery mode, priority, and time-to-live values configured on the template. Some providers may set their own default QoS on the ConnectionFactory; enabling this flag makes the template explicitly pass the configured values.

With ProducerCallback, you can pass per-message QoS directly in producer.send(message, deliveryMode, priority, timeToLive) without altering the template's global settings.

### Delivery delay

JMS 2.0 added delivery delay for message producers. Supported versions of JmsTemplate can configure a shared delivery delay via setDeliveryDelay(...); if per-producer delay is needed, the corresponding MessageProducer API can be used.

Delivery delay is not time-to-live:

- Delivery delay: the provider withholds delivering the message to consumers until the delay elapses.
- Time-to-live: the message expires after a duration from send time.

Verify whether the provider fully supports these QoS features. Brokers may enforce their own limits or policies.

## 5. Session Transactions and Commit/Rollback Boundaries

By default, JmsTemplate creates a non-transacted Session using AUTO_ACKNOWLEDGE when no transaction is active. You can configure sessionTransacted or use a Spring transaction manager to change this behavior.

Three cases must be distinguished:

1. **Non-transacted Session:** no JMS commit/rollback boundary managed by the Session.
2. **Locally transacted Session:** the application or Session owner must decide commit/rollback.
3. **Transaction-manager-managed Session:** Spring transaction infrastructure coordinates commit/rollback; callback code must not manually commit a managed Session.

### Low-level callbacks do not auto-commit for the application

execute(SessionCallback) and execute(ProducerCallback) are low-level APIs. The callback is invoked to perform operations on the Session/Producer; do not assume that merely returning normally from a callback automatically commits all changes in a transacted Session.

If the callback uses an application-managed locally transacted Session, clearly define where commit() or rollback() is called. If the Session participates in a Spring-managed or JTA transaction, let the transaction manager coordinate; do not call commit/rollback manually on that Session.

Example configuring JmsTemplate for a local transacted Session:

~~~java
@Bean
JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setSessionTransacted(true);
    return template;
}
~~~

For transactions coordinating multiple JMS operations under a Spring transaction, you can use JmsTransactionManager for a single ConnectionFactory:

~~~java
@Bean
JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory
) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

A business method can then run inside a Spring-managed transaction:

~~~java
@Transactional(transactionManager = "jmsTransactionManager")
public void publishOrderEvents() {
    // Operations via JmsTemplate participate in the active JMS transaction.
}
~~~

JmsTransactionManager manages JMS transactions for a single ConnectionFactory. If distributed transactions coordinating JMS with a database or other resources are needed, compatible JTA/XA infrastructure is required; a local JMS transaction does not automatically make database operations part of the same transaction.

### Note when using SessionCallback

Do not call session.commit() or session.rollback() arbitrarily inside a callback. First determine whether the Session is local or managed by a transaction manager. Calling manual commit on a managed Session can break Spring's transaction boundaries.

## 6. Synchronous Receiving, Selectors, and Timeouts

JmsTemplate supports synchronous receiving via receive(...), receiveSelected(...), and receiveAndConvert(...) variants.

Example:

~~~java
jmsTemplate.setReceiveTimeout(2_000L);

Message message = jmsTemplate.receiveSelected(
        queue,
        "eventType = 'OrderCreated' AND schemaVersion >= 2"
);

if (message == null) {
    // No matching message within wait period.
}
else {
    // Process received message.
}
~~~

A message selector is a JMS expression based on headers and properties. It does not arbitrarily parse fields inside a JSON body. If filtering by eventType or schemaVersion is required, the producer must set those values as JMS properties.

Synchronous receive blocks the calling thread until a message arrives or the timeout expires. Do not leave indefinite timeouts on HTTP request handlers or bounded thread pools without load controls.

### Browsing a queue with QueueBrowser

If you need to inspect messages sitting in a queue without consuming them, use browse(...) with BrowserCallback:

~~~java
public List<String> browseMessageIds(Queue queue) {
    return jmsTemplate.browse(queue, (session, browser) -> {
        List<String> ids = new ArrayList<>();
        Enumeration<?> messages = browser.getEnumeration();

        while (messages.hasMoreElements()) {
            Message message = (Message) messages.nextElement();
            ids.add(message.getJMSMessageID());
        }

        return ids;
    });
}
~~~

QueueBrowser only inspects queue contents; it does not remove messages the way a receiving consumer does. The enumeration and browse results reflect the queue state at the moment the provider executes the operation. Do not use browse as a message-locking mechanism or as a substitute for a consumer.

## 7. Built-in Request/Reply in JmsTemplate

When you only need to send a request and receive one reply, usually prefer sendAndReceive(...) over manually creating a temporary queue with SessionCallback.

Example:

~~~java
Message reply = jmsTemplate.sendAndReceive(
        requestQueue,
        session -> {
            TextMessage request = session.createTextMessage(
                    "{\"orderId\":\"ORD-1001\"}"
            );
            request.setJMSCorrelationID("lookup-1001");
            return request;
        }
);
~~~

JmsTemplate creates a temporary queue, sets that destination in JMSReplyTo, sends the request, and waits for a reply per the configured receive timeout. If no reply arrives within the wait time, the result may be null.

Use SessionCallback when you need finer control over steps such as creating custom consumers, using selectors, managing temporary destinations, or executing multiple operations on the same Session.

## 8. Resource Lifecycle Inside Callbacks

Resource-closing rules depend on who created the object:

| Object | Created By | Closed By |
|---|---|---|
| Connection opened by JmsTemplate | JmsTemplate | JmsTemplate |
| Session supplied by JmsTemplate | JmsTemplate | JmsTemplate |
| Producer passed to ProducerCallback | JmsTemplate | JmsTemplate |
| Producer created manually in SessionCallback | Application | Application |
| Consumer created manually in SessionCallback | Application | Application |
| TemporaryQueue/TemporaryTopic created by code | Application | Application calls delete when done |

Do not close the Session or Producer passed by JmsTemplate into a callback. If you manually create producers/consumers inside SessionCallback, close them in finally, even when send or receive fails.

Do not store Sessions, producers, or consumers in fields for reuse across calls. If resource creation optimization is needed, consider CachingConnectionFactory or a provider-appropriate connection pool.

## 9. Exceptions and Error Handling

Jakarta JMS methods commonly throw checked JMSException. Callbacks are permitted to throw this exception; JmsTemplate translates errors into Spring JMS's unchecked JmsException hierarchy.

Common scenarios:

- Destination does not exist or cannot be resolved.
- Producer fails to send because the broker disconnected.
- Message is invalid according to the provider.
- Consumer receive times out and returns null.
- Transaction commit or rollback fails.
- Provider rejects QoS or unsupported features.

When retrying, distinguish transient failures from non-recoverable errors. Retry only appropriate failures, cap retry counts, and apply backoff. For sends that may duplicate after a connection drop when it is unclear whether the broker accepted the message, consumers should implement idempotency based on a business event ID or stable business key.

Do not catch and ignore JMSException. If a callback cannot complete the operation, let the exception propagate through JmsTemplate or translate it into a domain error with a clear cause.

## 10. Java 17 Project Example with Spring JMS 6.2

The code snippets above are integration methods used in a service already configured with JmsTemplate and Destinations. They do not start a broker themselves. To compile the examples, the project needs Spring JMS and the Jakarta Messaging API.

### Maven dependencies

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-jms</artifactId>
        <version>6.2.19</version>
    </dependency>

    <dependency>
        <groupId>jakarta.jms</groupId>
        <artifactId>jakarta.jms-api</artifactId>
        <version>3.1.0</version>
    </dependency>
</dependencies>
~~~

### Example service

Place the sendBatch, requestReply, and browseMessageIds methods in a service class whose constructor accepts JmsTemplate. Configure a ConnectionFactory and Destinations appropriate for your broker. This example uses the jakarta.jms namespace, fitting Spring Framework 6.x.

A minimal service can be declared as:

~~~java
package com.example.messaging;

import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.UUID;

import jakarta.jms.DeliveryMode;
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;

import org.springframework.jms.core.JmsTemplate;

public class JmsCallbackOperations {

    private final JmsTemplate jmsTemplate;

    public JmsCallbackOperations(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public int sendBatch(Destination destination, List<String> payloads) {
        return jmsTemplate.execute(destination, (session, producer) -> {
            for (int i = 0; i < payloads.size(); i++) {
                TextMessage message = session.createTextMessage(payloads.get(i));
                message.setIntProperty("batchIndex", i);
                message.setStringProperty("eventType", "OrderEvent");

                producer.send(
                        message,
                        DeliveryMode.PERSISTENT,
                        4,
                        60_000L
                );
            }
            return payloads.size();
        });
    }

    public String requestReply(Destination requestDestination, String body) {
        return jmsTemplate.execute(session -> {
            TemporaryQueue replyQueue = session.createTemporaryQueue();
            MessageProducer producer = null;
            MessageConsumer consumer = null;

            try {
                producer = session.createProducer(requestDestination);
                consumer = session.createConsumer(replyQueue);

                String correlationId = UUID.randomUUID().toString();
                TextMessage request = session.createTextMessage(body);
                request.setJMSReplyTo(replyQueue);
                request.setJMSCorrelationID(correlationId);
                producer.send(request);

                Message reply = consumer.receive(3_000L);
                if (reply == null) {
                    return null;
                }
                if (!(reply instanceof TextMessage textReply)) {
                    throw new JMSException("Expected a TextMessage reply");
                }
                if (!correlationId.equals(reply.getJMSCorrelationID())) {
                    throw new JMSException("Reply correlation ID does not match");
                }
                return textReply.getText();
            }
            finally {
                try {
                    if (consumer != null) {
                        consumer.close();
                    }
                }
                finally {
                    try {
                        if (producer != null) {
                            producer.close();
                        }
                    }
                    finally {
                        replyQueue.delete();
                    }
                }
            }
        }, true);
    }

    public List<String> browseMessageIds(Queue queue) {
        return jmsTemplate.browse(queue, (session, browser) -> {
            List<String> ids = new ArrayList<>();
            Enumeration<?> messages = browser.getEnumeration();

            while (messages.hasMoreElements()) {
                Message message = (Message) messages.nextElement();
                ids.add(message.getJMSMessageID());
            }

            return ids;
        });
    }
}
~~~

The class above compiles with the stated dependencies, but running it in practice requires a JMS provider, ConnectionFactory, configured queues/topics, and a corresponding request/reply receiving service. There is no fixed stdout because results depend on messages in the broker and responses from the consumer.

## 11. Common Misconceptions

1. **"SessionCallback automatically commits when the callback returns."** Do not assume that. The callback is a low-level Session access API; you must determine who manages the transaction.
2. **"ProducerCallback needs to manually close the passed-in producer."** Incorrect. The producer is created and managed by JmsTemplate within that callback.
3. **"SessionCallback can share a Session across multiple threads."** Incorrect. Sessions and their associated resources are not meant for arbitrary sharing across threads.
4. **"ProducerCallback can only send one message."** Incorrect. You can send multiple messages through the same producer in one callback.
5. **"JmsTemplate QoS always applies automatically."** Delivery mode, priority, and TTL configured on the template require explicitQosEnabled=true; ProducerCallback can pass per-send QoS directly.
6. **"Synchronous receive has no timeout."** JmsTemplate has receiveTimeout; choose an appropriate value because receive blocks the calling thread.
7. **"QueueBrowser removes messages from the queue."** Incorrect. A browser only inspects messages; consumers receive and consume messages.
8. **"TemporaryQueue lives indefinitely."** Temporary destinations are tied to the lifecycle of the connection that created them; manage and delete them when no longer used.
9. **"A local JMS transaction includes the database."** Incorrect. A proper transaction coordinator and XA are required if coordinating multiple resources in one distributed transaction.
10. **"A successful send proves the consumer finished processing."** Incorrect. Send results only reflect the send operation per provider semantics; business completion requires a separate reply, acknowledgment, or event.

## 12. Key Takeaways

- **SessionCallback<T>** supplies a Session to execute multiple JMS operations in a single callback.
- **ProducerCallback<T>** supplies a Session and MessageProducer to send multiple messages or customize QoS.
- JmsTemplate manages resources it creates; the application must close producers/consumers/temporary destinations created by the callback itself.
- send(message, deliveryMode, priority, timeToLive) allows setting QoS per message.
- execute(SessionCallback, true) starts the Connection when the callback needs to receive messages.
- receiveSelected uses selectors on headers/properties; browse inspects a queue without consuming messages.
- Low-level callbacks require understanding transactions and Session lifecycles; do not manually commit a Session managed by Spring/JTA.
- Use sendAndReceive for standard request/reply; use SessionCallback when fine-grained JMS API control is needed.
- Keep idempotency, timeouts, retries, and error handling explicit when working with brokers.

When choosing a callback, start from the object you need to control: to only create a message, use MessageCreator; to access Session, use SessionCallback; to access Session together with producer, use ProducerCallback. Resource and transaction boundaries must be established before adding advanced JMS operations.
