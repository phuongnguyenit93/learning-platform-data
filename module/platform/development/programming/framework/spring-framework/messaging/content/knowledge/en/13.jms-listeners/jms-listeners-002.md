# MessageListenerAdapter and Mapping to Object Methods

## Objectives

In Spring JMS, `MessageListenerAdapter` lets you use a POJO as a message-driven listener without requiring the POJO to directly implement `jakarta.jms.MessageListener`. The adapter receives the JMS message from the listener container, converts the message content into a suitable Java type, and then invokes a method on the delegate object.

This mechanism separates the message-processing business logic from the JMS API. The delegate can accept only `String`, `byte[]`, `Map`, or a Java type produced by a converter.

After this lesson, you can:

- Explain the position of `MessageListenerAdapter` in Spring JMS.
- Distinguish the adapter from `jakarta.jms.MessageListener` and `SessionAwareMessageListener`.
- Attach a POJO as a delegate and choose the message-receiving method.
- Understand the default method name, `setDefaultListenerMethod`, and overloading by parameter type.
- Control the conversion of a JMS Message into a payload using the Spring JMS `MessageConverter`.
- Receive a raw message such as `TextMessage` when needed.
- Create a reply from the return value and route it through `JMSReplyTo` or the default response destination.
- Configure the adapter together with a listener container and handle errors/transactions.
- Distinguish this adapter from the `@JmsListener` mechanism.
- Run a request/reply example with Spring Boot and embedded ActiveMQ Artemis.

## 1. What Problem Does MessageListenerAdapter Solve?

JMS defines the standard interface `jakarta.jms.MessageListener` with a single callback:

~~~java
public interface MessageListener {
    void onMessage(Message message);
}
~~~

A class implementing this interface must work directly with the JMS Message. If the message is a `TextMessage`, the listener calls `getText()` itself; if it is a `BytesMessage`, the listener reads the bytes itself; if metadata is needed, the listener must access the JMS headers/properties.

Example of a listener tightly coupled to JMS:

~~~java
public class RawOrderListener implements MessageListener {

    @Override
    public void onMessage(Message message) {
        if (message instanceof TextMessage textMessage) {
            try {
                String orderId = textMessage.getText();
                processOrder(orderId);
            }
            catch (JMSException ex) {
                throw new IllegalStateException(ex);
            }
        }
    }

    private void processOrder(String orderId) {
        // Business logic
    }
}
~~~

This approach is valid, but the business class must know about JMS. When you want to reuse the processing logic from REST, a scheduler, or another kind of messaging, this dependency causes difficulty.

`MessageListenerAdapter` acts as a bridge:

~~~text
JMS Provider / Broker
        |
        v
Listener Container
        |
        v
MessageListenerAdapter
        |
        +--> read the JMS Message
        |
        +--> MessageConverter
        |
        +--> choose the method on the delegate
        |
        v
POJO delegate (business logic)
        |
        +--> void/null: processing only
        |
        +--> object: converted into a JMS reply if there is a reply destination
~~~

The delegate can be an ordinary POJO, with no need to import the JMS API and no need to implement `MessageListener`.

## 2. Components and Packages to Know

`MessageListenerAdapter` lives in the package:

~~~java
org.springframework.jms.listener.adapter.MessageListenerAdapter
~~~

Related components:

| Component | Package | Role |
|---|---|---|
| `MessageListenerAdapter` | `org.springframework.jms.listener.adapter` | Converts the JMS callback into a delegate method call. |
| `AbstractAdaptableMessageListener` | `org.springframework.jms.listener.adapter` | Provides the infrastructure for payload extraction, the converter, and sending the response. |
| `MessageListener` | `jakarta.jms` | The standard JMS callback with `onMessage(Message)`. |
| `SessionAwareMessageListener` | `org.springframework.jms.listener` | A Spring callback that additionally provides the JMS Session so a reply can be sent within the same session. |
| `MessageConverter` | `org.springframework.jms.support.converter` | Converts a JMS Message into an object and an object into a JMS Message. |
| `DefaultMessageListenerContainer` | `org.springframework.jms.listener` | Manages the consumer, threads, session, transactions, and listener lifecycle. |
| `JmsTemplate` | `org.springframework.jms.core` | Sends and receives messages synchronously. |

Do not confuse the Spring JMS `MessageConverter` with `org.springframework.messaging.converter.MessageConverter`. The two interfaces have different packages and different conversion boundaries.

## 3. How Does the Adapter Work?

When the broker delivers a message to the listener container, the container calls the adapter. The adapter performs these main steps:

1. Receives the JMS `Message` and, in Spring's calling path, may additionally receive the `Session`.
2. Extracts the content from the JMS message using the `MessageConverter`.
3. Determines the name of the delegate method to call.
4. Builds the parameter list and finds a compatible method on the delegate.
5. Invokes the method via reflection.
6. If the method returns a non-null object and a suitable session is available, converts the object into a JMS response message and sends it to the response destination.

Example:

~~~java
MessageListenerAdapter adapter =
        new MessageListenerAdapter(new OrderDelegate());

adapter.setDefaultListenerMethod("processOrder");
~~~

When it receives a `TextMessage` containing `ORD-42`, the default converter can extract the String `"ORD-42"`. The adapter calls:

~~~java
delegate.processOrder("ORD-42");
~~~

The POJO does not need to know that the original message was a JMS `TextMessage`. If the converter is changed, the same delegate method can receive a different payload type.

## 4. The Delegate Object and the Default Method

There are two ways to provide the processing method:

- Pass a delegate object to the constructor or call `setDelegate`.
- Do not pass a delegate; in that case the processing methods must be defined in a subclass of the adapter.

Example delegate:

~~~java
public class OrderDelegate {

    public void handleMessage(String orderId) {
        System.out.println("processing order=" + orderId);
    }
}
~~~

Adapter configuration:

~~~java
@Bean
MessageListenerAdapter orderMessageListener(OrderDelegate delegate) {
    return new MessageListenerAdapter(delegate);
}
~~~

The default method name is `handleMessage`. This is the value of the constant `ORIGINAL_DEFAULT_LISTENER_METHOD`.

If the POJO uses a different name, configure it explicitly:

~~~java
@Bean
MessageListenerAdapter orderMessageListener(OrderDelegate delegate) {
    MessageListenerAdapter adapter = new MessageListenerAdapter(delegate);
    adapter.setDefaultListenerMethod("processOrder");
    return adapter;
}
~~~

The corresponding delegate:

~~~java
public class OrderDelegate {

    public void processOrder(String orderId) {
        System.out.println("processing order=" + orderId);
    }
}
~~~

The name in `setDefaultListenerMethod` must match a method that can be invoked on the delegate. If the name is wrong or there is no method matching the parameter after conversion, dispatching to the delegate fails.

`setDefaultListenerMethod` only sets the default method name. It does not create the method by itself and does not decide the queue/topic.

## 5. Mapping by Parameter Type and Method Overloading

The adapter can use multiple methods with the same name but accepting different payload types.

~~~java
public class MessageDelegate {

    public void handleMessage(String text) {
        System.out.println("text=" + text);
    }

    public void handleMessage(Map<?, ?> values) {
        System.out.println("map=" + values);
    }

    public void handleMessage(byte[] bytes) {
        System.out.println("bytes=" + bytes.length);
    }

    public void handleMessage(Serializable value) {
        System.out.println("serializable=" + value.getClass().getSimpleName());
    }
}
~~~

If the converter extracts the payload as a String, the adapter looks for an overload compatible with String. If the converter returns a Map or byte array, the matching overload may be chosen.

This organization is useful when a destination receives multiple kinds of JMS message. However, you need to design the method signatures clearly:

- Avoid multiple overloads whose parameter types are too broad and all compatible with the same payload.
- Prefer specific types such as String, Map, or byte array.
- If different formats require different business flows, use separate method names or separate destinations so the code is easy to read.
- Do not assume the adapter reads an arbitrary header by itself and then changes the method name. By default, the method name is the configured name.

In the default implementation, `getListenerMethodName(originalMessage, extractedMessage)` returns the default listener method. You can subclass `MessageListenerAdapter` and override this method if you need to choose the method name based on the JMS message or the extracted content. This is an advanced extension point; you must explicitly check the message type, that the method exists, and the routing policy.

## 6. The Default MessageConverter and the Payload Types the Delegate Receives

`MessageListenerAdapter` uses the Spring JMS `SimpleMessageConverter` by default. This converter extracts the appropriate content from common JMS message types:

| JMS message | Payload the delegate typically receives |
|---|---|
| `TextMessage` | `String` |
| `BytesMessage` | `byte[]` |
| `MapMessage` | `Map` |
| `ObjectMessage` | Serializable object |
| JMS `Message` without a body | Depends on the message type and the converter |

Examples:

- Sending a `TextMessage` containing `ORD-42`: the delegate method can receive a `String`.
- Sending a `BytesMessage`: the delegate method can receive a `byte[]`.
- Sending a `MapMessage`: the delegate method can receive a `Map`.

This is a Spring JMS conversion, not automatic JSON serialization. If you need JSON to POJO, configure a suitable JSON converter in Spring JMS and agree on the schema between producer/consumer.

### Setting a Custom Converter

~~~java
MessageListenerAdapter adapter = new MessageListenerAdapter(delegate);
adapter.setMessageConverter(customJmsMessageConverter);
~~~

The converter is used in both directions:

- Inbound: the JMS Message becomes the parameter of the delegate method.
- Outbound: the object returned from the delegate becomes the JMS response Message.

If the converter cannot convert the payload, the adapter cannot call the delegate with the desired type. Check the conversion error, the JMS message type, and the target parameter.

### When You Want to Receive the Raw JMS Message

If the delegate needs to read the JMS headers and properties directly or call specific APIs such as `TextMessage.getText()`, you can turn off automatic conversion by setting the converter to null:

~~~java
MessageListenerAdapter adapter = new MessageListenerAdapter(delegate);
adapter.setDefaultListenerMethod("receiveRaw");
adapter.setMessageConverter(null);
~~~

The delegate receives the JMS Message object:

~~~java
public class RawDelegate {

    public void receiveRaw(TextMessage message) throws JMSException {
        System.out.println("raw text=" + message.getText());
    }
}
~~~

When the converter is null, the delegate method must accept the exact JMS Message type that is sent. The example above requires the message to be a `TextMessage`; if another type is received, the call may fail because the parameter type is incompatible.

## 7. How Does the Adapter Support Replies?

An important capability is that the delegate method can return an object. If the result is non-null, the adapter can convert it into a JMS Message and send a response.

Example:

~~~java
public class OrderDelegate {

    public String processOrder(String orderId) {
        return "accepted:" + orderId;
    }
}
~~~

When it receives the request `ORD-42`, the method returns `"accepted:ORD-42"`. With the default converter, a String is typically converted into a JMS `TextMessage`.

The adapter determines the response destination in this order:

1. The destination in the request's JMS header `JMSReplyTo`.
2. The default response destination configured on the adapter.
3. If there is no destination at all, the adapter throws `InvalidDestinationException`.

You can configure a default response destination:

~~~java
adapter.setDefaultResponseQueueName("orders.reply");
~~~

Or pass a `Destination` object:

~~~java
adapter.setDefaultResponseDestination(replyQueue);
~~~

If the application needs a default topic, the corresponding API is `setDefaultResponseTopicName`. The adapter uses the `DestinationResolver` to resolve the response destination name.

### No Reply When the Method Returns void or null

- A method returning `void`: the adapter has no response object to send.
- A method returning `null`: the adapter does not send a response.
- A method returning a non-null object: the adapter handles the response destination and sends a JMS message.

If the method returns an object but the request has no `JMSReplyTo` and the adapter has no default destination, request processing may fail because the place to send the response cannot be determined. Only return a response when the reply path has been designed.

### Replying Requires SessionAwareMessageListener

`MessageListenerAdapter` implements both the JMS `MessageListener` and the Spring `SessionAwareMessageListener`. However, the two entry points do not have the same capabilities:

| Entry point | Has a Session? | Can send a response from the return value? |
|---|---|---|
| `onMessage(Message)` of the JMS `MessageListener` | No | No |
| `onMessage(Message, Session)` of the Spring `SessionAwareMessageListener` | Yes | Yes |

When the adapter is used within a Spring listener container, the container can call the SessionAware entry point so the adapter sends the reply using the current session. If you register the adapter directly as a standard JMS `MessageListener` outside the SessionAware mechanism, do not rely on the return value to send a response.

This is why the request/reply example should use a Spring listener container.

## 8. MessageListenerAdapter and the Listener Container

The adapter does not connect to the broker by itself and does not subscribe to a queue/topic by itself. The listener container is responsible for:

- Creating and managing the connection/session/consumer.
- Registering the listener with the destination.
- Receiving messages and calling the adapter.
- Managing threads, concurrency, recovery, and lifecycle.
- Applying the acknowledgement/transaction policy.

Configuration example:

~~~java
@Bean
MessageListenerAdapter orderMessageListener(OrderDelegate delegate) {
    MessageListenerAdapter adapter = new MessageListenerAdapter(delegate);
    adapter.setDefaultListenerMethod("processOrder");
    return adapter;
}

@Bean
DefaultMessageListenerContainer orderListenerContainer(
        ConnectionFactory connectionFactory,
        MessageListenerAdapter orderMessageListener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.queue");
    container.setMessageListener(orderMessageListener);
    container.setSessionTransacted(true);
    return container;
}
~~~

`setDestinationName` lets the container resolve the destination by name. For a queue by default, the domain must be configured correctly. If the application uses a topic, you need to configure the corresponding pub-sub domain and ensure the broker has a suitable topic.

### Why Is a Listener Container Needed?

If you only create the adapter without registering it with the provider or a listener container, the adapter will not receive messages by itself.

In a Spring application, the container is usually `DefaultMessageListenerContainer` or `SimpleMessageListenerContainer`. `DefaultMessageListenerContainer` suits most use cases that need concurrency, recovery, and flexible transactions.

## 9. Errors and Transactions

Errors can appear at many stages:

| Stage | Example |
|---|---|
| JMS receive | The provider or connection fails. |
| Payload extraction | The MessageConverter cannot read the message type/body. |
| Method resolution | The delegate has no suitable method or the method name is misconfigured. |
| Delegate execution | The business logic throws an exception. |
| Reply conversion | The returned object is not supported by the converter. |
| Reply routing | There is no JMSReplyTo/default destination or the destination is invalid. |
| Reply send | The provider refuses to send the response or the session fails. |

How an exception is handled depends on the entry point and the container:

- With the JMS entry point `MessageListener.onMessage(Message)`, the adapter calls `handleListenerException` when an error occurs; the default implementation logs the error.
- With the Spring `SessionAwareMessageListener` entry point, the exception is propagated back to the caller/container for handling.
- The listener container decides the transaction, rollback, recovery, and redelivery according to configuration.
- It is not the default that every exception is returned to the producer. A producer that has sent a request usually needs to receive errors through a separate reply/error protocol.

### Local JMS Transaction

You can enable a local transaction on the listener container:

~~~java
container.setSessionTransacted(true);
~~~

When the listener fails during processing, the session may roll back and the broker redelivers the message according to the provider's semantics. A reply sent through the same session is part of that local JMS transaction.

A database transaction does not automatically participate in the same local JMS transaction. If the database has committed but JMS rolls back, the message may be redelivered and the business logic runs again. Therefore the delegate needs to be idempotent or use an event/business key to detect duplicate processing.

If you need a transaction coordinating JMS and the database, you need XA/JTA or an architecture such as a transactional outbox that fits the system's requirements.

## 10. The Delegate Must Be Thread-Safe

The listener container can run multiple consumers concurrently. A singleton delegate can be called by multiple threads at the same time.

Therefore:

- Prefer a stateless delegate, holding dependencies via constructor injection.
- Do not store the current payload in a shared field.
- Do not use an unsynchronized mutable collection to store message results.
- If there is a shared cache or counter, use a thread-safe structure or appropriate synchronization.
- Configure concurrency based on the capacity of the database and downstream services, not only on the number of threads that can be created.

A common mistake is using a `currentOrderId` field in the delegate and then assuming only one message is processed at a time. When the container increases concurrency, data between two messages can overwrite each other.

## 11. Distinguishing MessageListenerAdapter from @JmsListener

The two mechanisms are related but are not the same class:

| Mechanism | Main component | How it works |
|---|---|---|
| Classic POJO adapter | `MessageListenerAdapter` | Calls the delegate method by the default/configured name and the converted payload type. |
| Annotation-based endpoint | `@JmsListener` and `MessagingMessageListenerAdapter` | Uses the method invocation infrastructure, argument resolvers, annotations, and the message handler method factory. |

Annotation example:

~~~java
@Component
public class AnnotatedOrderListener {

    @JmsListener(destination = "orders.queue")
    public String processOrder(String orderId) {
        return "accepted:" + orderId;
    }
}
~~~

The `@JmsListener` mechanism can use `@SendTo` to specify the response destination:

~~~java
@JmsListener(destination = "orders.queue")
@SendTo("orders.reply")
public String processOrder(String orderId) {
    return "accepted:" + orderId;
}
~~~

Choose `MessageListenerAdapter` when you need to attach a POJO or a delegate method to a JMS listener container through explicit configuration. Choose `@JmsListener` when you want to declare the endpoint directly on the method, use annotations to bind the payload/header, and manage replies through messaging annotations.

Do not use `@JmsListener` and `MessageListenerAdapter` as if they were two names for the same class. Spring uses `MessagingMessageListenerAdapter` for annotation-based endpoints.

## 12. Runnable Java 17+ Example: POJO Delegate and Request/Reply

The example uses Spring Boot 4.1.2 and embedded ActiveMQ Artemis. The application sends a JMS request to `orders.queue`, with the request setting `JMSReplyTo` to `orders.reply`; the adapter converts the TextMessage to a String, calls the POJO method, and sends the String response back to the reply queue.

### Project Structure

~~~text
message-listener-adapter-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          MessageListenerAdapterApplication.java
          OrderDelegate.java
      resources/
        application.properties
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>message-listener-adapter-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>

        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.queue,orders.reply
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

The configuration above creates two queues in the embedded broker. This is an in-memory demo configuration, not a durability configuration for production.

### OrderDelegate.java

~~~java
package demo;

public class OrderDelegate {

    public String processOrder(String orderId) {
        System.out.println("delegate received=" + orderId);
        return "accepted:" + orderId;
    }
}
~~~

This POJO does not implement `MessageListener` and does not import `jakarta.jms`.

### MessageListenerAdapterApplication.java

~~~java
package demo;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.TextMessage;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.adapter.MessageListenerAdapter;

@SpringBootApplication
public class MessageListenerAdapterApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(MessageListenerAdapterApplication.class, args)) {
            // ApplicationRunner sends the request and waits for the reply.
        }
    }

    @Bean
    OrderDelegate orderDelegate() {
        return new OrderDelegate();
    }

    @Bean
    MessageListenerAdapter orderMessageListener(OrderDelegate delegate) {
        MessageListenerAdapter adapter = new MessageListenerAdapter(delegate);
        adapter.setDefaultListenerMethod("processOrder");
        return adapter;
    }

    @Bean
    DefaultMessageListenerContainer orderListenerContainer(
            ConnectionFactory connectionFactory,
            MessageListenerAdapter orderMessageListener) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.queue");
        container.setMessageListener(orderMessageListener);
        container.setSessionTransacted(true);
        return container;
    }

    @Bean
    ApplicationRunner requestReply(
            JmsTemplate jmsTemplate) {

        return args -> {
            jmsTemplate.setReceiveTimeout(5_000);

            jmsTemplate.send("orders.queue", session -> {
                TextMessage request = session.createTextMessage("ORD-42");
                request.setJMSReplyTo(session.createQueue("orders.reply"));
                return request;
            });

            Object response = jmsTemplate.receiveAndConvert("orders.reply");
            if (!(response instanceof String reply)) {
                throw new IllegalStateException("No String reply received");
            }

            System.out.println("reply=" + reply);
        };
    }
}
~~~

Run with Java 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

The stdout lines printed by the application (ignoring the Spring Boot startup log):

~~~text
delegate received=ORD-42
reply=accepted:ORD-42
~~~

### Explanation of the Execution Flow

1. Spring Boot initializes embedded Artemis and the two queues `orders.queue` and `orders.reply`.
2. Spring creates the `OrderDelegate` POJO.
3. `MessageListenerAdapter` receives the delegate and configures the default method as `processOrder`.
4. `DefaultMessageListenerContainer` registers the adapter as the listener of `orders.queue`.
5. `JmsTemplate` sends a TextMessage containing `ORD-42` and sets `JMSReplyTo` to `orders.reply`.
6. The container receives the request and calls the adapter through the SessionAware entry point.
7. The default converter converts the TextMessage into a String.
8. The adapter calls `OrderDelegate.processOrder("ORD-42")`.
9. The delegate returns `accepted:ORD-42`; the adapter converts the String into a TextMessage and sends it to the destination in `JMSReplyTo`.
10. `JmsTemplate.receiveAndConvert` receives the reply and converts the TextMessage into a String.

`receiveTimeout` is set so the program does not wait indefinitely if the listener or the reply path fails. `sessionTransacted=true` lets the request receive and the response send participate in the same local JMS transaction. The database or external systems still need their own transaction/idempotency.

## 13. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| The delegate method cannot be invoked | The default method name is wrong or there is no suitable method | Check `setDefaultListenerMethod` and the parameter after conversion |
| The delegate receives a TextMessage instead of a String | The converter is set to null or a custom converter returns the raw message | Check `setMessageConverter` |
| The delegate needs a TextMessage but receives a String | The default converter is extracting the body | Set the converter to null if you truly need the raw JMS Message |
| The overloaded method is not chosen as expected | The payload type is compatible with multiple overloads | Use a specific type or a separate method name |
| The reply cannot be sent | The request lacks `JMSReplyTo` and the adapter has no default response destination | Set JMSReplyTo or configure a default response destination |
| The reply is sent to the wrong queue/topic | The reply destination or resolver is incorrect | Check JMSReplyTo, the resolver, and destination provisioning |
| The method returns null but the client waits for a reply | No response is sent | Define null/void semantics explicitly or return a response object |
| The return value cannot be converted into a JMS Message | The MessageConverter does not support the return type | Configure a suitable converter |
| The listener exception does not reach the producer | The exception is handled at the adapter/container; request/reply has no error protocol | Design an error response or a separate error destination |
| Duplicate message processing | Rollback/redelivery or a crash after the business logic has committed | Use an idempotency key and an appropriate transaction |
| The delegate has a race condition | The listener container calls the same delegate from multiple threads | Keep the delegate stateless/thread-safe |

## 14. Deployment Checklist

- [ ] The delegate is a POJO with a method that accepts the payload in the type the converter produces.
- [ ] The method name matches the default listener method or custom routing.
- [ ] The method signature is unambiguous when using overloads.
- [ ] The converter matches the JMS message type and payload format.
- [ ] Only turn off the converter when the delegate truly needs the raw JMS Message.
- [ ] The listener container registers the adapter with the correct queue/topic.
- [ ] If the method returns an object, there is a JMSReplyTo or a default response destination.
- [ ] The reply converter supports the return type.
- [ ] The reply flow uses the SessionAwareMessageListener entry point.
- [ ] Transaction/acknowledgement/redelivery are configured deliberately.
- [ ] The delegate is thread-safe when the container concurrency is greater than one.
- [ ] There are tests with a valid payload, a wrong type, a nonexistent method, a missing reply-to, and a reply send failure.
- [ ] Do not log the whole message if the body/properties contain sensitive data.

## Key Takeaways

- `MessageListenerAdapter` lives in `spring-jms` and turns a POJO into a message-driven listener.
- By default the adapter calls `handleMessage`; use `setDefaultListenerMethod` to choose a different name.
- The adapter uses the Spring JMS `SimpleMessageConverter` by default to extract the payload as a String, byte array, or Map.
- Use a null converter if you want the delegate to receive the raw JMS Message such as `TextMessage`.
- A delegate method that returns a non-null object can produce a JMS response message.
- The reply is sent first to the request's `JMSReplyTo`; if there is none, the default response destination is used.
- Replying requires the `SessionAwareMessageListener` entry point; the standard JMS `MessageListener.onMessage(Message)` does not send a response from the return value.
- The listener container manages the connection, consumer, transaction, recovery, and adapter lifecycle.
- `@JmsListener` uses `MessagingMessageListenerAdapter`, which is a separate annotated endpoint mechanism.
- The delegate needs to be thread-safe and idempotent when handling asynchronously, with retries, or with redelivery.

## Official Documentation

- [Spring Framework Reference 7.0: Receiving a Message](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/receiving.html)
- [Spring Framework 7.0.10 Javadoc: MessageListenerAdapter](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/listener/adapter/MessageListenerAdapter.html)
- [Spring Framework 7.0.10 Javadoc: AbstractAdaptableMessageListener](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/listener/adapter/AbstractAdaptableMessageListener.html)
- [Spring Framework Javadoc: DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework Javadoc: MessageConverter for JMS](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/MessageConverter.html)
- [Spring Framework Reference: Annotated JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/annotated.html)
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
