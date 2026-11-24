# send, receive, and sendAndReceive

## Learning Objectives

After this lesson, you will be able to:

- Distinguish one-way send operations from sending a request and waiting for a reply.
- Understand the roles of MessageChannel.send(), PollableChannel.receive(), and methods on MessagingTemplate.
- Choose the right channel for send, receive, and request-reply.
- Explain how replyChannel is used to match responses to requests.
- Configure send timeout and receive timeout, and handle cases with no reply.
- Distinguish Spring Messaging's low-level API from Spring Integration's utility template.
- Avoid confusing a channel accepting a message with a consumer finishing business processing.

## 1. The Big Picture

In Spring Messaging, a producer creates a Message and sends it to a MessageChannel. A consumer can retrieve messages by polling if the channel supports PollableChannel, or be invoked by the channel via a MessageHandler if the channel supports SubscribableChannel.

The three operations send, receive, and sendAndReceive represent three exchange styles:

| Operation | Meaning | Typical Outcome |
|---|---|---|
| send | Sends a Message to a channel | Send confirmation or exception depending on the API called |
| receive | Pulls a Message from a pollable channel | A Message or null when the wait time expires |
| sendAndReceive | Sends a request and waits for the corresponding response | Reply Message or null on timeout |

There are two API layers to distinguish:

- **Low-level channel API:** MessageChannel.send() and PollableChannel.receive(). These are the core contracts of Spring Messaging.
- **Messaging template:** provides convenient operations for sending, receiving, converting payloads, and performing request-reply. Spring Framework has GenericMessagingTemplate in the org.springframework.messaging.core package. Spring Integration provides MessagingTemplate in the org.springframework.integration.core package, extending GenericMessagingTemplate and adding integration with Spring Integration's channel system.

The method names are similar, but return types and responsibilities can differ. In particular, MessageChannel.send() returns boolean, whereas MessagingTemplate.send() is a void method and signals send failures via exceptions.

## 2. send: Sending a Message

### 2.1. Sending Directly via MessageChannel

MessageChannel defines the send contract. Two commonly used methods:

~~~java
boolean send(Message<?> message);

boolean send(Message<?> message, long timeout);
~~~

The send(message) method sends according to the implementation's policy. It may wait indefinitely if the channel needs to block before accepting the Message.

The send(message, timeout) method bounds the wait time in milliseconds. The constant MessageChannel.INDEFINITE_TIMEOUT indicates no wait time limit.

Return values:

- true: the channel accepted the Message.
- false: the channel could not accept the Message under current conditions, such as a timeout or the send being interrupted.
- RuntimeException: an unrecoverable or delivery error depending on the implementation.

Example:

~~~java
Message<String> message = MessageBuilder
        .withPayload("ORD-89")
        .setHeader("eventType", "order.created")
        .build();

boolean accepted = channel.send(message, 500);

if (!accepted) {
    System.out.println("Message was not accepted");
}
~~~

A true return value does not assert that the handler has finished processing, that a transaction has committed, or that a broker has persisted the message durably. It only reflects that the send was accepted under the channel's contract.

### 2.2. Sending with MessagingTemplate

The template helps applications call messaging APIs more conveniently. Example with Spring Integration:

~~~java
MessagingTemplate template = new MessagingTemplate();
template.setSendTimeout(500);

template.send(channel, message);
~~~

MessagingTemplate.send(destination, message) returns void. When the method returns normally, the send operation has completed under the template's contract. If the channel does not accept the Message or a delivery error occurs, the template can throw MessagingException or a specialized exception in the messaging system.

Key differences to remember:

| API | Return Type | How Send Failure Is Signaled |
|---|---|---|
| MessageChannel.send(message) | boolean | Check for false or catch exception |
| MessageChannel.send(message, timeout) | boolean | Check for false or catch exception |
| MessagingTemplate.send(channel, message) | void | Catch MessagingException/MessageDeliveryException |

Do not write code assuming these two send methods return the same data type.

### 2.3. send and convertAndSend

If you already have a Message, use send. If you only have a payload and want the template to create the Message, you can use convertAndSend:

~~~java
template.convertAndSend(channel, "ORD-89");
~~~

The template uses the configured MessageConverter to convert the payload into a Message. You can also pass headers or a MessagePostProcessor when you need to add metadata or adjust the Message after conversion.

MessageConverter is not a broker and does not automatically guarantee every payload is serialized to JSON. The conversion depends on the configured converter and supported data types.

## 3. receive: Actively Pulling a Message

### 3.1. PollableChannel Is a Key Requirement

receive only suits channels that support polling. PollableChannel extends MessageChannel and provides:

~~~java
Message<?> receive();

Message<?> receive(long timeout);
~~~

The consumer actively calls receive to pull a Message. With receive() without a timeout, the implementation may block indefinitely if no message is available yet. With receive(timeout), the thread waits at most the specified number of milliseconds.

If the timeout expires or receiving is interrupted, PollableChannel can return null.

Example:

~~~java
Message<?> received = pollableChannel.receive(1_000);

if (received == null) {
    System.out.println("No message received");
}
else {
    System.out.println("payload=" + received.getPayload());
}
~~~

You cannot call receive on a SubscribableChannel just because it is also a MessageChannel. SubscribableChannel delivers messages by subscribing a MessageHandler; it does not provide a polling contract.

### 3.2. receive with MessagingTemplate

MessagingTemplate.receive(destination) is a convenient wrapper for the receive operation. The template uses the configured receive timeout:

~~~java
template.setReceiveTimeout(1_000);

Message<?> received = template.receive(pollableChannel);
~~~

The target must be a PollableChannel. GenericMessagingTemplate checks this condition; if the channel does not support polling, the receive operation is invalid and can throw IllegalStateException.

If no Message arrives within the wait period, receive returns null. The application must check for null before reading the payload or headers.

### 3.3. receiveAndConvert

When the application only needs the payload converted to a specific type, you can use receiveAndConvert:

~~~java
String payload = template.receiveAndConvert(pollableChannel, String.class);
~~~

The template receives the Message and then uses MessageConverter to convert the payload to the requested type. If no Message is received within the timeout, the result can be null. If conversion fails, the template can throw MessageConversionException.

Use receive when you need both headers and payload. Use receiveAndConvert when you only need the converted payload and do not need to keep the envelope.

## 4. sendAndReceive: Request-Reply in One Operation

### 4.1. When Is Request-Reply Needed?

send is one-way: the producer emits a Message and does not automatically receive a business outcome.

There are situations where the producer needs a corresponding response:

- Sending a request to check an order's status and needing the result.
- Asking a service to calculate a price and waiting for the price to come back.
- Sending an inventory check command and needing to know the remaining quantity.
- Invoking an internal handler and needing a response Message.

This is the request-reply pattern. The producer sends a request and waits for a reply. The sendAndReceive method combines those two operations into one API:

~~~java
Message<?> reply = template.sendAndReceive(channel, request);
~~~

The result is a reply Message, or null if no response is received within the receive timeout. Send or messaging errors can be reported via MessagingException.

### 4.2. What Is replyChannel Used For?

The template needs to know where to send the reply back. When sendAndReceive is called, GenericMessagingTemplate creates a temporary reply channel for that exchange and attaches this channel to the request's replyChannel header.

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant A as Requester
    participant T as MessagingTemplate
    participant C as Request Channel
    participant H as Handler
    participant R as Temporary Reply Channel

    A->>T: sendAndReceive(request)
    T->>T: Create temporary reply channel
    T->>C: Send request with replyChannel header
    C->>H: Forward request to handler
    H->>R: Send response to replyChannel
    R-->>T: Return reply Message
    T-->>A: sendAndReceive returns reply
~~~

The handler must honor replyChannel if implementing request-reply handling manually at the MessageHandler level. In Spring Integration, endpoints such as service activators can automatically handle return values and route replies according to endpoint configuration.

If the handler does not send a reply or sends the reply to the wrong channel, the requester will wait until receive timeout and receive null. A response sent to another channel does not automatically become the reply for a waiting sendAndReceive call.

### 4.3. Request and Reply Are Two Messages

The request and reply are two independent Messages. The reply can have a different payload, different headers, and carry metadata related to the request.

You should preserve a correlation ID or business identifier if you need to trace the exchange across multiple systems. The temporary reply channel helps the template match the reply to the waiting call, while correlation IDs are useful for logging, tracing, and communication across brokers.

Do not confuse correlation ID with replyChannel. Correlation ID is identifying metadata for the application to track requests/responses; replyChannel is the reply-receiving address used by the messaging infrastructure.

## 5. Configuring Timeouts for send and receive

GenericMessagingTemplate has two independent timeouts:

- sendTimeout: maximum time to wait for the channel to accept the request Message.
- receiveTimeout: maximum time to wait for a reply or a received Message.

Example:

~~~java
template.setSendTimeout(500);
template.setReceiveTimeout(2_000);
~~~

In request-reply, sendTimeout applies to the request-sending step. receiveTimeout applies to the reply-waiting step.

If receiveTimeout is too short, the reply may arrive after the requester has timed out. When a reply arrives late, the temporary reply channel is no longer awaited by the requester. GenericMessagingTemplate has the setThrowExceptionOnLateReply option to decide whether to throw MessageDeliveryException when a reply arrives late or just log a warning by default.

The default timeouts on GenericMessagingTemplate are -1, meaning no wait time limit. In real applications, configure explicit timeouts to avoid holding threads indefinitely.

A timeout does not prove the request was not processed. The consumer may still be processing after the requester's wait time expires. If the producer re-sends, the business operation may execute twice. For operations with side effects, design an idempotency key or deduplication mechanism.

## 6. Runnable Java 17 Example: send, receive, and sendAndReceive

The following example uses Spring Integration's MessagingTemplate together with QueueChannel and DirectChannel. QueueChannel illustrates polling-style send/receive; DirectChannel illustrates request-reply with replyChannel.

### 6.1. Maven Configuration

Create the file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>messaging-operations-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.5.10</version>
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

Spring Integration core provides MessagingTemplate, QueueChannel, and DirectChannel. This artifact transitively brings in the compatible spring-messaging dependency.

### 6.2. Complete Program

Create the file src/main/java/demo/MessagingOperationsDemo.java:

~~~java
package demo;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

public class MessagingOperationsDemo {

    public static void main(String[] args) {
        MessagingTemplate template = new MessagingTemplate();
        template.setSendTimeout(1_000);
        template.setReceiveTimeout(1_000);

        demonstrateSendAndReceive(template);
        demonstrateSendAndReceiveReply(template);
    }

    private static void demonstrateSendAndReceive(MessagingTemplate template) {
        QueueChannel queue = new QueueChannel(10);

        Message<String> outbound = MessageBuilder
                .withPayload("ORD-89")
                .setHeader("eventType", "order.created")
                .build();

        // MessagingTemplate.send() returns void.
        // If sending fails, the template reports the error via an exception.
        template.send(queue, outbound);
        System.out.println("send.completed=true");

        Message<?> received = template.receive(queue);

        if (received == null) {
            throw new IllegalStateException("Expected a message from the queue");
        }

        System.out.println("receive.payload=" + received.getPayload());
        System.out.println(
                "receive.eventType=" + received.getHeaders().get("eventType")
        );

        // The queue is now empty. Wait only 100 ms for the next receive.
        template.setReceiveTimeout(100);
        Message<?> empty = template.receive(queue);
        System.out.println("receive.empty=" + (empty == null));
    }

    private static void demonstrateSendAndReceiveReply(
            MessagingTemplate template) {

        DirectChannel requestChannel = new DirectChannel();

        requestChannel.subscribe(request -> {
            Object replyHeader =
                    request.getHeaders().get(MessageHeaders.REPLY_CHANNEL);

            if (!(replyHeader instanceof MessageChannel replyChannel)) {
                throw new IllegalStateException("Request has no reply channel");
            }

            Message<String> reply = MessageBuilder
                    .withPayload("accepted:" + request.getPayload())
                    .build();

            if (!replyChannel.send(reply)) {
                throw new IllegalStateException("Reply channel rejected the reply");
            }
        });

        template.setReceiveTimeout(1_000);

        Message<String> request = MessageBuilder
                .withPayload("ORD-89")
                .setHeader("requestType", "inventory.check")
                .build();

        Message<?> reply = template.sendAndReceive(requestChannel, request);

        if (reply == null) {
            throw new IllegalStateException("No reply received before timeout");
        }

        System.out.println("request.payload=" + request.getPayload());
        System.out.println("reply.payload=" + reply.getPayload());
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.MessagingOperationsDemo
~~~

Stdout:

~~~text
send.completed=true
receive.payload=ORD-89
receive.eventType=order.created
receive.empty=true
request.payload=ORD-89
reply.payload=accepted:ORD-89
~~~

### 6.3. Program Analysis

In the first part, the producer creates a Message with payload ORD-89 and header eventType. template.send puts the Message into QueueChannel. The template's send method returns void; when it returns normally, the program continues. The consumer calls template.receive to pull the Message from the queue.

The next receive has no Message, because QueueChannel has already been drained. The template waits only 100 milliseconds and returns null. The program checks for null and prints receive.empty=true.

In the request-reply part, DirectChannel delivers the request to the registered MessageHandler. The template attaches a temporary reply channel to the replyChannel header. The handler extracts that header, builds a response Message, and sends it to the temporary channel. sendAndReceive receives the reply and returns it to the caller.

Because the example uses DirectChannel, the handler runs directly during the send call. With an asynchronous channel or adapter, the handler may run on another thread; the requester still waits for the reply until it arrives or the receive timeout expires.

## 7. When to Use Each Operation?

| Need | Suitable API | Notes |
|---|---|---|
| Emit an event, no reply needed | send | Only confirms send per channel/template |
| Send a payload not yet wrapped in a Message | convertAndSend | Template uses MessageConverter |
| Pull a Message from a queue or pollable channel | receive | Requires PollableChannel |
| Pull a payload and convert it to a Java type | receiveAndConvert | Depends on MessageConverter |
| Send a request and wait for a reply | sendAndReceive | Requires handler or endpoint sending response to replyChannel |
| Send a request and receive a converted payload | convertSendAndReceive | Requires appropriate converter |
| Send to a channel and process asynchronously one-way | send | Choose channel/adapter with appropriate dispatch |

A helpful selection rule:

- Use send when the caller only needs to emit a message.
- Use receive when the caller actively pulls a Message from a pollable channel.
- Use sendAndReceive when the caller needs a response corresponding to the request.
- Use convertAndSend or convertSendAndReceive when you want the template to handle payload conversion.

Do not use sendAndReceive merely to check that a channel received a request. If no business response is needed, send is simpler and avoids holding a thread waiting for a reply.

## 8. Common Errors and How to Handle Them

### 8.1. Calling receive on a SubscribableChannel

SubscribableChannel has no polling contract. It pushes Messages to registered MessageHandlers. To call receive, use a PollableChannel or an implementation that supports polling.

### 8.2. Not Checking for null

receive and sendAndReceive can return null when receive timeout expires or no Message is available. Always check the result before reading the payload.

### 8.3. Confusing MessageChannel.send's boolean with MessagingTemplate.send's void

MessageChannel.send returns boolean. MessagingTemplate.send returns void and signals errors via exceptions. Read the API signature carefully to handle send outcomes accurately.

### 8.4. Waiting for a Reply When the Handler Sends No Response

sendAndReceive requires a reply. If the handler only processes the request without sending a response, the caller will wait until receive timeout and get null. If the business flow does not need a reply, use send.

### 8.5. Sending the Reply to the Wrong Channel

When the template creates a temporary reply channel, the handler must send the response to the channel in the replyChannel header. Sending a reply to another channel does not complete the waiting sendAndReceive call.

### 8.6. Setting Timeouts Too Short or Infinite

A timeout that is too short makes the requester give up before the consumer finishes processing. An infinite timeout can hold threads for a long time and exhaust resources. Choose timeouts according to target latency and handle the no-reply case.

### 8.7. Retrying After Timeout Without Deduplication

A timeout only indicates that the requester did not receive a reply in time. The consumer may still have performed side effects. Re-sending the request can create duplicate effects. Use an idempotency key, request ID, or deduplication mechanism when needed.

### 8.8. Thinking Successful send Means Business Completion

send only reflects that the channel accepted the Message. It does not replace business-level acknowledgment, transaction commit, or durable broker persistence confirmation.

### 8.9. Not Handling MessagingException

Template operations can throw MessagingException or specific exceptions such as MessageDeliveryException or MessageConversionException. Categorize send failures, conversion failures, timeouts, and handler errors to decide whether to retry or return an error to the caller.

## 9. Notes on Modules and Implementations

Foundational APIs belong to Spring Framework:

- MessageChannel and the send method.
- PollableChannel and the receive method.
- Message, MessageHeaders, and MessageBuilder.
- GenericMessagingTemplate and the MessageSendingOperations, MessageReceivingOperations, and MessageRequestReplyOperations interfaces.

Spring Integration adds:

- MessagingTemplate in the org.springframework.integration.core package, extending GenericMessagingTemplate.
- QueueChannel and DirectChannel.
- Endpoints and integration flows that can handle request-reply, pollers, adapters, and routing automatically.

Therefore, do not assume that merely adding spring-messaging gives you QueueChannel or DirectChannel. If using Spring Integration implementations, you need the corresponding spring-integration-core dependency. If using Spring Framework's foundational APIs, choose GenericMessagingTemplate and channel implementations appropriate for your architecture.

An in-memory channel also does not automatically become a durable broker. Characteristics such as persistence, acknowledgment, redelivery, ordering, and exactly-once semantics depend on the adapter/broker and actual configuration.

## 10. Self-Check Questions

1. What data type does MessageChannel.send() return?
2. How does MessagingTemplate.send() differ from MessageChannel.send() in return type and error reporting?
3. Why is receive only suitable for PollableChannel?
4. When receive timeout expires, what is the typical result?
5. How does sendAndReceive differ from send in its reply requirement?
6. Which header does the template use to send a reply back to the right waiting request?
7. What happens if the handler does not send a reply?
8. Which two phases do sendTimeout and receiveTimeout control?
9. Why does a timeout not prove a request was not processed?
10. When should you use convertSendAndReceive instead of sendAndReceive?
11. Does GenericMessagingTemplate belong to Spring Framework or Spring Integration?
12. Which module do QueueChannel and DirectChannel belong to?

## 11. Conclusion

send, receive, and sendAndReceive represent three different communication needs. send emits a Message to a channel; receive actively pulls a Message from a pollable channel; sendAndReceive sends a request and waits for a corresponding reply.

When working at the low level, remember that MessageChannel.send returns boolean and PollableChannel.receive can return null. When using MessagingTemplate, send is void, receive uses the configured timeout, and sendAndReceive requires a reply sent back to replyChannel. Configuring timeouts, handling exceptions, and checking for null help the application maintain better control when channels reject sends or consumers do not respond on time.

## Official References

- Spring Framework MessageChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html
- Spring Framework PollableChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html
- Spring Framework GenericMessagingTemplate API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html
- Spring Framework MessageSendingOperations API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessageSendingOperations.html
- Spring Framework MessageRequestReplyOperations API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessageRequestReplyOperations.html
- Spring Integration MessagingTemplate reference: https://docs.spring.io/spring-integration/reference/channel/template.html
- Spring Integration MessagingTemplate API: https://docs.spring.io/spring-integration/api/org/springframework/integration/core/MessagingTemplate.html
