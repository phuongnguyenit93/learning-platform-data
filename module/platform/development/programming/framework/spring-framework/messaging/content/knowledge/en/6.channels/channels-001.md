# MessageChannel and the send Contract in Spring Messaging

## 1. What Is MessageChannel?

In Spring Framework, **org.springframework.messaging.MessageChannel** is the abstraction representing the sending end of messages. A publisher only needs to know the channel and call **send(message)**; it does not need to know which handler is receiving, how it is registered, or which thread it is running on.

A **Message<?>** contains a payload and headers. **MessageChannel** accepts that message and delegates processing to the concrete implementation. This interface focuses on the send operation and does not define how messages are received or how subscribers are registered.

Spring Messaging uses the following related abstractions:

- **Message<T>**: the data being sent, consisting of a typed payload and headers.
- **MessageChannel**: the message sending contract.
- **SubscribableChannel**: extends MessageChannel and manages registered MessageHandlers to process incoming messages.
- **PollableChannel**: extends MessageChannel and allows consumers to actively call receive() to retrieve messages.
- **MessageHandler**: the contract for handling messages via handleMessage(message).

The relationships can be visualized as follows:

~~~mermaid
classDiagram
    class MessageChannel {
        +send(Message) boolean
        +send(Message, timeout) boolean
    }
    class SubscribableChannel {
        +subscribe(MessageHandler) boolean
        +unsubscribe(MessageHandler) boolean
    }
    class PollableChannel {
        +receive() Message
        +receive(timeout) Message
    }
    MessageChannel <|-- SubscribableChannel
    MessageChannel <|-- PollableChannel
~~~

**MessageChannel** is an interface in the **org.springframework.messaging** package, belonging to the **spring-messaging** module. It is also used as a common abstraction across other Spring components, including Spring Integration.

## 2. Two send Methods

In Spring Framework 7.0.10, MessageChannel declares two ways to send:

~~~java
boolean send(Message<?> message);

boolean send(Message<?> message, long timeout);
~~~

**send(Message<?>)** is a default method. It calls the timeout overload with **MessageChannel.INDEFINITE_TIMEOUT**, meaning no wait deadline is set. Depending on the implementation, this call may wait indefinitely.

**send(Message<?>, long timeout)** sends the message and may block until the channel accepts the message or the timeout expires. The timeout unit is milliseconds; the value **MessageChannel.INDEFINITE_TIMEOUT** is **-1L**, indicating an unlimited wait time.

| Call | Meaning |
| --- | --- |
| **send(message)** | Sends without specifying a timeout; the implementation may block indefinitely |
| **send(message, 500)** | Allows the implementation to wait up to a 500-millisecond timeout |
| **send(message, MessageChannel.INDEFINITE_TIMEOUT)** | Sends with an unlimited wait time |

The timeout only controls the wait time according to the implementation's capabilities. **MessageChannel** does not mandate that every channel have a buffer, capacity, or the same policy when timeout equals 0. Read the contract of the specific channel before relying on those details.

## 3. Meaning of the Return Value

Both **send** methods return a **boolean**:

- **true**: the message was accepted by the channel or sent successfully according to the implementation's contract.
- **false**: the message was not sent for a non-fatal reason, such as the channel being unable to accept the message within the specified timeout or the send operation being interrupted.
- **RuntimeException**: may be thrown when an unrecoverable error occurs.

Do not interpret **true** as "the consumer has finished processing." It only confirms the send result according to the channel. Depending on the channel type, the message may have just been handed off to a handler, placed in a queue, or handed off to an executor. Completing business processing, durable storage, or receiving an acknowledgment from a broker are different levels of guarantees.

Example of checking the send result:

~~~java
boolean sent = channel.send(message, 500);

if (sent) {
    System.out.println("Message accepted by channel");
} else {
    System.out.println("Message was not accepted");
}
~~~

If sending fails, the application needs to decide how to handle it based on business requirements: log, emit an alert, retry with a limit, store in an outbox, or return an error to the caller. Do not automatically retry indefinitely because it can increase load or create duplicate messages.

When catching exceptions, catch the specific error types that the implementation or calling layer can throw. Do not catch generic Exception and ignore it, as doing so hides programming and operational errors.

## 4. MessageChannel Does Not Determine How Messages Are Received

**MessageChannel** only defines how to send. Subinterfaces add how consumers receive messages:

| Channel type | How consumer retrieves messages | Characteristics |
| --- | --- | --- |
| **SubscribableChannel** | Handlers register beforehand using subscribe | Channel actively invokes handlers when a message arrives |
| **PollableChannel** | Consumers call receive() or receive(timeout) | Consumers actively pull messages; the implementation may buffer |
| Plain **MessageChannel** | No receive API defined by the interface | Only knows the send contract; handling depends on the implementation |

With **SubscribableChannel**, **subscribe(handler)** returns true if registration succeeds and false if the handler is already registered. **unsubscribe(handler)** returns true if unregistration succeeds and false if the handler was not registered.

With **PollableChannel**, **receive()** may block indefinitely waiting for a message. **receive(timeout)** waits for a message for the specified duration; returns null if the timeout expires or the thread is interrupted.

Do not call **receive()** on a **MessageChannel** just because the variable is named "channel". Only types implementing the **PollableChannel** contract provide a polling API; only **SubscribableChannel** provides a subscriber management API.

## 5. Implementations Affect send Behavior

The interface unifies how calls are made, while the implementation determines how messages are delivered, how long calls block, and how errors are reported.

### 5.1. ExecutorSubscribableChannel in Spring Framework

**ExecutorSubscribableChannel** is an implementation of **SubscribableChannel** within Spring Framework itself. It delivers messages to each registered subscriber.

- The no-argument constructor dispatches messages on the thread calling send.
- The constructor accepting an Executor dispatches messages through the provided executor.
- It provides subscribe and unsubscribe to manage handlers.
- When using an executor, dispatch can be asynchronous; send returning does not mean all handlers have finished processing.

Example of configuring a channel in an application:

~~~java
@Bean
public SubscribableChannel orderEvents() {
    return new ExecutorSubscribableChannel();
}
~~~

The example above uses the no-argument constructor. Handlers run on the thread calling send. To move dispatch to a thread pool, pass a properly configured Executor with managed lifecycle.

### 5.2. Channels in Spring Integration

Spring Integration adds many implementations to serve integration flows. Some common names:

- **DirectChannel**: distributes point-to-point to a matching handler; the handler is typically invoked directly on the sending thread.
- **PublishSubscribeChannel**: broadcasts messages to multiple subscribers.
- **QueueChannel**: stores messages in a queue for consumer polling.
- **PriorityChannel**: a queue that orders messages by priority.

Classes such as **DirectChannel**, **PublishSubscribeChannel**, and **QueueChannel** belong to Spring Integration, not the core implementations of the **spring-messaging** module. To use them, the project needs the corresponding Spring Integration dependency.

When reading code, check imports and dependencies to know whether the channel in use comes from Spring Framework or Spring Integration. Both ecosystems share the **MessageChannel** abstraction, but their implementation lists and operational configurations differ.

## 6. Runnable Example with Spring Framework 7.0.10 and Java 17+

The following example uses **ExecutorSubscribableChannel** to illustrate a publisher depending only on the **MessageChannel** interface. The channel is created with the no-argument constructor, so the handler runs synchronously on the sending thread.

Directory structure:

~~~text
message-channel-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── MessageChannelDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>message-channel-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>MessageChannelDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/MessageChannelDemo.java**

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class MessageChannelDemo {

    public static void main(String[] args) {
        SubscribableChannel channel = new ExecutorSubscribableChannel();

        channel.subscribe(message ->
            System.out.println("handler.payload=" + message.getPayload())
        );

        Message<String> event = MessageBuilder
            .withPayload("order-72")
            .setHeader("eventType", "order.created")
            .build();

        MessageChannel publisherPort = channel;
        boolean sent = publisherPort.send(event);

        System.out.println("sent=" + sent);
    }
}
~~~

Run in the directory containing **pom.xml**:

~~~bash
mvn -q clean compile exec:java
~~~

Stdout:

~~~text
handler.payload=order-72
sent=true
~~~

**publisherPort** has type **MessageChannel**, even though the actual object is **ExecutorSubscribableChannel**. The publisher only calls send; handler registration is managed via **SubscribableChannel**. Because the channel uses the no-argument constructor, the handler runs on the thread calling send, so the handler.payload line appears before sent=true.

### 6.1. Demonstrating the Timeout Overload

You can replace the **send(event)** call with:

~~~java
boolean sent = publisherPort.send(event, 500);
~~~

The value 500 is the wait time in milliseconds. For a specific channel, read the implementation's documentation to see how waiting applies. For example, **ExecutorSubscribableChannel** does not have a queue-style buffer to wait for a slot; do not assume all channels block or time out the same way.

### 6.2. Demonstrating the Contract with Lambdas

**MessageChannel** is annotated with **@FunctionalInterface**. In a unit test or simple example, you can write a minimal implementation using a lambda:

~~~java
MessageChannel acceptingChannel = (message, timeout) -> true;
MessageChannel rejectingChannel = (message, timeout) -> false;
~~~

The two lambdas above only demonstrate two possible outcomes of the send contract. They do not store messages, do not deliver messages to consumers, and do not simulate a real broker.

## 7. Channel Interceptors and Control Points When Sending

Some Spring Framework implementations support **InterceptableChannel**, allowing a **ChannelInterceptor** to be attached to the message path. Interceptors are useful for logging, metrics, tracing, inspecting metadata, or blocking messages based on policy.

Commonly used callbacks:

- **preSend(message, channel)**: runs before the message is sent. Can return a transformed message or null to block sending.
- **postSend(message, channel, sent)**: runs after the send operation and receives the boolean result.
- **afterSendCompletion(message, channel, sent, exception)**: runs after the send process completes, even if an exception occurred.

Example of an interceptor that logs the send result:

~~~java
public class SendLoggingInterceptor implements ChannelInterceptor {

    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent) {
        System.out.println(
            "channel=" + channel + ", sent=" + sent
        );
    }
}
~~~

Registering the interceptor on a channel that supports interception:

~~~java
ExecutorSubscribableChannel channel = new ExecutorSubscribableChannel();
channel.addInterceptor(new SendLoggingInterceptor());
~~~

An interceptor is an observation point and a place to apply cross-cutting concerns. Do not put full business logic inside an interceptor because it makes sending behavior hard to follow and hard to test.

## 8. Common Errors When Calling send

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| send returns false | Channel rejected the message, timeout expired, or sending thread was interrupted | Record the result; handle retry or fallback according to policy |
| send blocks for a long time | Implementation is waiting for capacity or waiting for the message to be accepted | Choose a finite timeout if appropriate and check channel configuration |
| send returns true but business logic is not finished | Channel accepted or dispatched the message, but the handler processes it later | Track processing results at the consumer or use an appropriate acknowledgment |
| No handler receives the message | Channel has no subscribers or the handler was unsubscribed | Check subscriptions, handler lifecycle, and channel type |
| Calling receive on a MessageChannel variable | The base interface does not define message reception | Use PollableChannel if consumers need polling |
| Sent via executor but logs appear later | Handler runs on an executor thread | Use logs with a correlation ID and monitor asynchronous errors |
| Retries cause duplicate processing | A previous send may have been accepted while the caller did not receive business confirmation | Design idempotent consumers and use an event ID |

## 9. Design Principles When Using MessageChannel

- Keep publishers depending on the **MessageChannel** interface to reduce coupling with implementations.
- Choose **SubscribableChannel** when handler registration is needed; choose **PollableChannel** when consumer polling is needed.
- Set timeouts appropriate for SLAs and channel capabilities; avoid defaulting to indefinite waits on critical request paths.
- Handle all three cases: true, false, and exceptions.
- Distinguish between the channel accepting a message and the consumer completing processing.
- When using an executor, configure the thread pool, queue, and rejection policy explicitly.
- Use a correlation ID to trace from publisher through handler.
- If messages must survive restarts or require durable acknowledgments, choose an appropriate broker and persistence configuration; **MessageChannel** itself provides no storage guarantees.
- Use interceptors for logging, metrics, and tracing; keep business logic inside handlers or services.

## 10. References

- [Spring Framework API — MessageChannel](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Spring Framework API — SubscribableChannel](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/SubscribableChannel.html)
- [Spring Framework API — PollableChannel](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/PollableChannel.html)
- [Spring Framework API — ExecutorSubscribableChannel](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [Spring Framework API — ChannelInterceptor](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Integration — Channel Interfaces](https://docs.spring.io/spring-integration/reference/7.0/channel/interfaces.html)
