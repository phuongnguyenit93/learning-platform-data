# preSend and How to Reject a Message in Spring Messaging

## 1. ChannelInterceptor in the Message Send Flow

Spring Messaging represents data as Message<T>, consisting of a payload and headers. MessageChannel is the point where messages are sent; the channel implementation determines how messages are delivered to subscribers or stored for consumers to receive.

**ChannelInterceptor** is an extension point that lets you observe, inspect, or transform a message as it passes through a channel. An interceptor is attached to a specific channel and participates in that channel's send/receive lifecycle.

The most important method when sending is:

~~~java
Message<?> preSend(Message<?> message, MessageChannel channel);
~~~

Spring calls preSend before the channel performs the dispatch. The return value decides the next step:

- **Returning the same message:** allows sending to proceed without modifying the message.
- **Returning a different message:** allows sending to proceed with the transformed message.
- **Returning null:** rejects the message; the channel stops the send process and does not dispatch that message to subscribers.

Thus, preSend can be used both to check conditions and to normalize or enrich metadata before a message is processed.

An interceptor affects only operations passing through the channel on which the interceptor is registered. Creating a GenericMessage or MessageBuilder on its own does not automatically trigger preSend; the message must be sent through a channel that has the interceptor.

## 2. Contract of preSend

### 2.1. Allowing a Message to Proceed

If no message changes are needed, return the received message object:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    return message;
}
~~~

This case applies when the interceptor only inspects or records information. After preSend returns the message, the channel proceeds with dispatch according to its implementation.

### 2.2. Rejecting by Returning null

To stop a message from proceeding, return null:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    if (!isAllowed(message)) {
        return null;
    }

    return message;
}
~~~

When preSend returns null, the send process is cancelled in the interceptor chain. With AbstractMessageChannel, the send call returns false and subscribers do not receive the rejected message.

This is a controlled rejection mechanism without needing to throw an exception for an expected business condition such as a payload missing a required field or containing an invalid value.

Distinguish two outcomes:

- **send returns false due to interceptor rejection:** the message is not passed to the channel handler.
- **send throws an exception:** the send operation encountered an error; the caller must handle the exception according to application policy.

Do not use null to hide infrastructure errors, programming bugs, or an inactive channel state. Choose the outcome according to the true meaning of the validation condition.

### 2.3. Rejecting with an Exception

An interceptor can also throw an exception when encountering an error that needs to be reported directly to the caller:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    if (message.getHeaders().get("tenantId") == null) {
        throw new IllegalArgumentException("tenantId is required");
    }

    return message;
}
~~~

When an exception escapes preSend, the send operation fails with an exception instead of returning false. The caller must distinguish expected exceptions from unexpected failures and avoid automatically retrying every exception.

Use an exception when the caller needs to know why sending cannot continue. For an ordinary rejection condition where the caller only needs to know the message was not accepted, returning null may be more appropriate.

## 3. Transforming a Message in preSend

preSend is not required to return the exact input instance. If you need to add headers or create a normalized payload, build a new message:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    return MessageBuilder
        .fromMessage(message)
        .setHeader("validated", true)
        .build();
}
~~~

The channel continues with the returned message. Subscribers receive the new message containing the validated header.

MessageBuilder.fromMessage copies the payload and headers into the builder. The original message is not modified; however, the payload object may still be the same reference. If you need to transform the payload content, create a new payload rather than mutating a shared mutable object.

Do not modify MessageHeaders directly because they are immutable. Creating a new message via MessageBuilder is the clean way to add or replace metadata.

### 3.1. Order of Validation and Transformation

An interceptor typically follows these steps:

1. Determine whether the payload is of the expected type.
2. Validate required fields and business rules.
3. Verify metadata that must be trusted, such as tenant or source, from an appropriate context.
4. Reject with null if conditions are not met.
5. Create a new message if verified headers need to be added.
6. Return the message so the channel continues dispatching.

Do not use a client-supplied header as proof of authentication. If a header affects permissions, tenant, or routing, verify it against the security context or a trusted application source.

## 4. Registering ChannelInterceptor on a Channel

ChannelInterceptor is not automatically applied to every MessageChannel in an application. It must be registered on an implementation that supports interceptors, typically AbstractMessageChannel or a subclass.

In Spring Framework Messaging, you can use ExecutorSubscribableChannel:

~~~java
ExecutorSubscribableChannel ordersChannel =
    new ExecutorSubscribableChannel();

ordersChannel.addInterceptor(new ChannelInterceptor() {
    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        if (!isAllowed(message)) {
            return null;
        }

        return message;
    }
});
~~~

You can register the interceptor when creating the channel bean:

~~~java
@Bean
ExecutorSubscribableChannel ordersChannel() {
    ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel();

    channel.addInterceptor(new OrderValidationInterceptor());
    return channel;
}
~~~

Registering on the right channel keeps the control scope clear. For example, only the channel receiving order-creation commands needs to validate OrderCommand; a channel sending logs or metrics can have a different policy.

If a channel is shared by multiple business flows, the interceptor must explicitly check the payload type and applicability conditions. Do not assume every message passing through the channel has the same payload type.

**Note on DirectChannel:** the familiar DirectChannel class belongs to the Spring Integration project, package org.springframework.integration.channel. The examples in this article use ExecutorSubscribableChannel from Spring Framework Messaging so the program only needs the spring-messaging dependency.

## 5. Other Callbacks in ChannelInterceptor

ChannelInterceptor provides multiple callbacks for the send and receive lifecycles:

| Callback | Timing and Purpose |
|---|---|
| preSend(message, channel) | Before sending; can transform or reject by returning null |
| postSend(message, channel, sent) | After the channel performs send; receives the sent result |
| afterSendCompletion(message, channel, sent, ex) | After send completes, even on error; suited for cleanup |
| preReceive(channel) | Before polling a message from a PollableChannel; return false not to receive |
| postReceive(message, channel) | After a message is received from a PollableChannel; can transform the received message |
| afterReceiveCompletion(message, channel, ex) | After the receive operation completes; suited for cleanup |

preSend controls **the send path**. For PollableChannel, preReceive controls **the receive path** with a boolean: return false to skip the receive operation on that call.

Do not confuse preSend with preReceive:

- preSend receives a Message<?> and can return a new message or null.
- preReceive receives a MessageChannel and returns a boolean because at that moment no message has been retrieved yet.

postSend receives the sent value to indicate how the channel reported the send outcome. It does not prove consumer business processing has completed. With an asynchronous channel, send may succeed while the handler is still processing.

afterSendCompletion and afterReceiveCompletion are useful for releasing resources or closing observation scopes after an operation finishes. Do not use cleanup callbacks to replace exception handling at the appropriate layer.

## 6. Message Rejection vs. Retry and Dead-Lettering

When preSend returns null, the message is blocked before the channel dispatches it. Spring Messaging does not automatically store blocked messages in a rejection queue, does not automatically retry, and does not automatically create a dead-letter queue.

If rejected messages must be retained for inspection, the application must proactively implement an appropriate mechanism, for example:

- Recording the rejection reason via metrics or audit logs with sensitive data stripped.
- Forwarding a safe copy of the message to a dedicated rejection channel, if the architecture allows.
- Persisting investigative details to access-controlled storage.
- Using retry/dead-letter mechanisms of the broker or Spring Integration when messages flow through the corresponding infrastructure.

Be careful when sending another message directly inside preSend. Sending to another channel can cause recursion, routing loops, or deadlock if two channels depend on each other. If a message must be routed to a rejection flow, design a separate path and avoid sending back to the channel currently being intercepted.

## 7. Designing Safe Rejection Conditions

### 7.1. Reject Only for Determinable Conditions

Rejection conditions should be clear and explainable. For example:

- The payload is not of a message type accepted by the channel.
- A required business field is missing.
- A value is outside defined bounds.
- The message has expired according to application rules.
- The verified identity or permission does not allow the operation.

Avoid vague conditions such as rejecting because a header “looks strange” without concrete validation rules.

### 7.2. Do Not Perform Slow Work in preSend

preSend sits on the message send path. If you execute database queries, HTTP calls, or wait on another service inside this callback, every send operation through the channel can be slowed down.

Prefer fast, deterministic, local checks. If remote verification is needed, consider a separate processing step with explicit timeouts and error policies.

### 7.3. Record the Reason for Rejection

If returning null, the caller usually only sees send return false. Design appropriate observability:

- Metrics counting rejected messages by reason category.
- Logs with correlation ID or message ID if present.
- Do not log full payloads or sensitive tokens.
- Separate counters can be used for invalid schema, business rule violations, and missing permissions.

Do not log secrets in headers or message content. If the rejection reason must be returned to the caller, use an intentional exception or a dedicated business response instead of relying solely on boolean false.

## 8. Standalone Runnable Java 17+ Example

The following example creates an ExecutorSubscribableChannel, registers a ChannelInterceptor, and adds a subscriber. The interceptor allows only OrderCommand instances with a positive amount. Valid messages are enriched with the validated header; messages with amount equal to 0 are rejected with null.

**Project Structure**

~~~text
presend-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          PreSendDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>presend-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.18</version>
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

**src/main/java/demo/PreSendDemo.java**

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class PreSendDemo {

    public record OrderCommand(String orderId, long amount) {}

    public static void main(String[] args) {
        ExecutorSubscribableChannel ordersChannel =
            new ExecutorSubscribableChannel();

        ordersChannel.addInterceptor(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(
                    Message<?> message,
                    MessageChannel channel) {

                if (!(message.getPayload() instanceof OrderCommand command)) {
                    return null;
                }

                if (command.amount() <= 0) {
                    return null;
                }

                return MessageBuilder
                    .fromMessage(message)
                    .setHeader("validated", true)
                    .build();
            }
        });

        ordersChannel.subscribe(message -> {
            OrderCommand command = (OrderCommand) message.getPayload();
            System.out.println(
                "handled=" + command.orderId()
                + ", validated=" + message.getHeaders().get("validated")
            );
        });

        Message<OrderCommand> validMessage = MessageBuilder
            .withPayload(new OrderCommand("ORD-1071", 125_000L))
            .build();

        Message<OrderCommand> invalidMessage = MessageBuilder
            .withPayload(new OrderCommand("ORD-1072", 0L))
            .build();

        boolean validSend = ordersChannel.send(validMessage);
        boolean invalidSend = ordersChannel.send(invalidMessage);

        System.out.println("validSend=" + validSend);
        System.out.println("invalidSend=" + invalidSend);
    }
}
~~~

Run from the presend-demo directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.PreSendDemo
~~~

**stdout**

~~~text
handled=ORD-1071, validated=true
validSend=true
invalidSend=false
~~~

The output shows:

- Message ORD-1071 has a positive amount, so preSend returns a message enriched with validated=true; the subscriber receives and processes the message.
- Message ORD-1072 has an amount of 0, so preSend returns null; the subscriber does not receive the message.
- send returns true for the valid message and false for the message rejected by the interceptor.

The example uses ExecutorSubscribableChannel without a configured executor, so the subscriber is invoked synchronously inside the send call. If an executor is configured, send returning true only indicates that the channel accepted/dispatched the message according to the channel's mechanism; it does not mean the handler has finished business processing.

## 9. Common Pitfalls

1. **Returning null while expecting the channel to retry automatically:** null only rejects the current send attempt. Retry or dead-lettering must be designed separately.
2. **Throwing an exception for every invalid case:** expected business errors can be represented with null and metrics; exceptions are for errors that must be reported directly.
3. **Returning the original message after building a copy:** if you want subscribers to receive the new header, you must return the newly built message.
4. **Mutating MessageHeaders directly:** headers are immutable. Use MessageBuilder to create a new message.
5. **Registering the interceptor on the wrong channel:** an interceptor runs only on the channel to which it is attached.
6. **Assuming preSend controls every entry point into the application:** messages may reach consumers through another channel or a transport that does not pass through the intercepted channel.
7. **Using an untrusted header as proof of authorization:** verify identity and permissions at the security boundary.
8. **Calling slow services inside preSend:** increases send-path latency and can cause bottlenecks.
9. **Assuming send=true means the consumer finished processing:** the send result does not replace consumer acknowledgement or transaction outcome.
10. **Sending failed messages back to the same intercepted channel:** easily creates loops or recursion. Use a separate rejection flow if rejected messages must be retained.

## 10. When Should You Use preSend?

Use preSend when you need a fast, synchronous validation step before a message enters a channel, such as checking payload type, required fields, size limits, or adding verified metadata.

If you need complex business orchestration, retries, persisting failed messages, dead-lettering, or remote authentication, use a dedicated component in the flow or broker instead of stuffing all logic into an interceptor.

Keep interceptors small, clearly scoped, and independently testable. Rejections must have measurable reasons, while accepted messages must preserve the payload/header contract expected by consumers.

## 11. References

- [ChannelInterceptor — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [AbstractMessageChannel — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html)
- [ExecutorSubscribableChannel — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [MessageBuilder — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)