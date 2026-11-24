# One-Way Sending and Request-Reply in Spring Messaging

In Spring Messaging, a message is sent through a channel for another component to process. There are two common exchange contracts:

- **One-way sending:** send a message and do not wait for a business result to be returned.
- **Request-reply:** send a request, provide a return path, and wait for the corresponding reply.

The main section below uses the API of the `spring-messaging` module in Spring Framework: `MessageChannel`, `MessageHeaders`, `MessageBuilder`, and `GenericMessagingTemplate`. Spring Integration adds higher-level gateways and endpoints; the final section distinguishes the two modules to avoid mixing up APIs.

## 1. Related Components

A message in Spring has two parts:

- **Payload:** the main data, such as `OrderCreated`, `String`, or a DTO.
- **Headers:** metadata such as message ID, timestamp, content type, correlation ID, reply channel, or error channel.

Core API types:

| Component | Role |
| --- | --- |
| `Message<T>` | Wraps payload and headers |
| `MessageChannel` | Entry point for sending messages to a processing flow |
| `MessageHandler` | Receives and processes messages |
| `SubscribableChannel` | Channel that invokes registered handlers |
| `PollableChannel` | Channel that can be read via `receive()` |
| `GenericMessagingTemplate` | Provides send, receive, and request-reply operations over `MessageChannel` |

`MessageChannel` defines the `send` operation; the interface itself does not define receiving a reply. Waiting for a reply requires a separate receiving mechanism, typically managed by a template.

## 2. One-Way Sending

### How It Works

Basic flow:

1. The sender creates a message.
2. The sender calls `MessageChannel.send(message)`.
3. The channel forwards the message to a handler or receiving infrastructure.
4. The sender continues without waiting for a business reply.

Example:

```java
Message<String> event = MessageBuilder
        .withPayload("order-created:42")
        .build();

boolean accepted = eventChannel.send(event);
```

The return value of `send` is a `boolean`:

- `true`: the channel accepted the message according to the channel's mechanism.
- `false`: the message was not sent successfully for a non-fatal reason, such as the channel being unable to accept it.
- An unrecoverable failure may be thrown as a runtime exception.

**Do not treat `true` as confirmation that business processing has completed.** By itself, it does not prove that the handler finished processing, that data was durably stored, or that an external system completed the work. The level of guarantee depends on the specific channel and transport.

### Runnable Example

This example uses `ExecutorSubscribableChannel` without passing an executor. With this constructor, the handler is invoked on the thread sending the message.

```java
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class OneWayDemo {

    public static void main(String[] args) {
        ExecutorSubscribableChannel events = new ExecutorSubscribableChannel();

        events.subscribe(message ->
                System.out.println("received: " + message.getPayload()));

        boolean accepted = events.send(
                MessageBuilder.withPayload("order-created:42").build());

        System.out.println("accepted: " + accepted);
    }
}
```

Output:

```text
received: order-created:42
accepted: true
```

In this example, the handler runs synchronously so the `received` line appears before the `accepted` line. That does not turn the contract into request-reply: the handler does not send a result back to the caller.

To run the example, use Java 17+ and Maven. Create the file `src/main/java/MessagingExchangeDemo.java` containing the request-reply example in the next section, then use the following minimal configuration in `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>messaging-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                    <mainClass>MessagingExchangeDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Command to run from the directory containing `pom.xml`:

```bash
mvn -q clean compile exec:java
```

If you want to run the `OneWayDemo` example separately, change `mainClass` to `OneWayDemo`.

If an `Executor` is passed to `ExecutorSubscribableChannel`, the channel can dispatch the handler through the executor. In that case, the handler can continue after the send call has returned. Therefore, distinguish between:

- **One-way** describes that the caller does not wait for a business reply.
- **Synchronous/asynchronous** describes when and on which thread the handler executes.

These two concepts are independent. A one-way operation can still invoke the handler synchronously.

### When to Use It?

Use one-way when the sender only needs to broadcast information or request processing, for example:

- Emitting an event that an order was just created.
- Sending notifications or telemetry.
- Recording an activity for another system to process.
- Triggering a background job where the caller does not need an immediate result.

If you need to know whether the job succeeded or failed, design a separate status event, callback, or status query API. Do not infer that outcome from the boolean returned by `send`.

## 3. Request-Reply

### How It Works

Request-reply adds a return path to a message:

1. The caller creates a request and sends it to a channel.
2. The caller waits for a reply on the reply channel.
3. The handler processes the request and sends the reply to that exact reply channel.
4. The template receives the reply and returns the message or payload to the caller.

In Spring Framework, `GenericMessagingTemplate.sendAndReceive(channel, request)` performs this exchange. The template creates a temporary reply channel for the invocation, places that channel into the `MessageHeaders.REPLY_CHANNEL` header, sends the request, and waits to receive the reply. Each invocation gets its own reply channel so concurrent requests do not share a single reply queue.

A handler at the `MessageHandler` layer must actively send the reply to the channel in the header. The `MessageHandler.handleMessage` interface does not automatically turn a method return value into a reply.

### Runnable Example

Create `src/main/java/MessagingExchangeDemo.java`:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.core.GenericMessagingTemplate;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class MessagingExchangeDemo {

    public static void main(String[] args) {
        // One-way: send an event without waiting for a business result.
        ExecutorSubscribableChannel events = new ExecutorSubscribableChannel();
        events.subscribe(message ->
                System.out.println("event received: " + message.getPayload()));

        boolean accepted = events.send(
                MessageBuilder.withPayload("order-created:42").build());
        System.out.println("event accepted: " + accepted);

        // Request-reply: handler sends the result back to the request's replyChannel.
        ExecutorSubscribableChannel requests = new ExecutorSubscribableChannel();
        requests.subscribe(request -> {
            String customer = (String) request.getPayload();
            Object replyTarget =
                    request.getHeaders().get(MessageHeaders.REPLY_CHANNEL);

            if (replyTarget instanceof MessageChannel replyChannel) {
                replyChannel.send(
                        MessageBuilder.withPayload("Hello, " + customer).build());
            }
        });

        GenericMessagingTemplate template = new GenericMessagingTemplate();
        template.setReceiveTimeout(2_000);

        Message<?> reply = template.sendAndReceive(
                requests,
                MessageBuilder.withPayload("Lan").build());

        System.out.println("request reply: "
                + (reply == null ? "<timeout>" : reply.getPayload()));
    }
}
```

Output:

```text
event received: order-created:42
event accepted: true
request reply: Hello, Lan
```

In the request-reply part, the template creates a temporary reply channel automatically. The handler reads the `MessageHeaders.REPLY_CHANNEL` header, casts it when the header contains a `MessageChannel`, and sends the reply message to that channel. If the handler does not send a reply, the caller waits until the receive timeout expires.

### `sendAndReceive` and `convertSendAndReceive`

| API | Input | Result |
| --- | --- | --- |
| `sendAndReceive(channel, request)` | A `Message<?>` | Reply as a `Message<?>` |
| `convertSendAndReceive(...)` | Payload, optional headers, and target type | Reply payload converted to the requested type |

Use `sendAndReceive` when you need to preserve the reply's message and headers. Use `convertSendAndReceive` when you want the template to convert the payload via a `MessageConverter` and return a specific Java type.

Request-reply methods can return `null` when no reply is received, such as on timeout. Therefore, handle the absent-result case rather than assuming a reply always exists.

## 4. Timeouts and Errors

Two types of timeouts must be distinguished:

| Timeout | Meaning |
| --- | --- |
| Send timeout | Maximum time to wait for the channel to accept the message when sending can block |
| Receive timeout | Maximum time to wait for a reply after the request is sent |

With `GenericMessagingTemplate`, you can configure:

```java
GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setSendTimeout(1_000);
template.setReceiveTimeout(2_000);
```

Timeout values are in milliseconds. In the current implementation, the default value for both send timeout and receive timeout is `-1`, meaning no wait limit. For request-reply, proactively set a finite receive timeout so the calling thread does not block indefinitely when a handler fails, produces no reply, or the message is misrouted.

When the receive timeout expires:

- `sendAndReceive` returns `null`.
- `convertSendAndReceive` may also return `null`.
- A late-arriving reply cannot be treated as the result of a call that has already finished. By default, the template logs a warning for late replies; you can enable `setThrowExceptionOnLateReply(true)` to throw `MessageDeliveryException`.

When sending fails, the template can throw `MessageDeliveryException`. Other messaging errors are typically represented by `MessagingException` or its subclasses. Distinguish between send failures, processing errors, and reply wait timeouts because their remedies differ.

With a channel that runs the handler on the calling thread, processing errors can surface directly in the sending flow. With a channel dispatching via an executor or a remote broker, a successful send does not mean processing errors will be thrown back to the sending thread. In those cases, design an error channel, dead-letter handling, logging, or error events suited to the transport.

## 5. Correlation and Reply Channels

In request-reply, the system must match a reply to the right request:

- With `GenericMessagingTemplate` and in-memory channels, the template creates a temporary reply channel per call.
- With brokers or remote transports, the reply channel can be mapped to a transport reply address. Systems typically need a correlation ID or equivalent mechanism to match responses to requests.
- Do not let multiple concurrent requests wait on a shared reply channel without a mechanism to distinguish and accurately route replies.

If implementing a request-reply protocol yourself, clearly define the request ID, correlation ID, reply destination, response deadline, and how late responses are handled. When retrying requests, consider an idempotency key to prevent duplicate business processing.

## 6. Choosing an Exchange Pattern

| Need | Suitable Pattern | Reason |
| --- | --- | --- |
| Broadcast an event without needing an immediate result | One-way | Sender does not have to hold a thread waiting for a reply |
| Invoke an operation and need the result to decide the next step | Request-reply | Result is returned directly to the caller |
| Long-running task where the caller should not wait | One-way + job ID/status or asynchronous processing | Avoids holding threads for a long duration |
| Need confirmation of acceptance | One-way with explicitly designed acknowledgement | Distinguishes acceptance confirmation from business outcome |

Request-reply suits lookups, validations, or calculations that need an immediate result. For long-running tasks, it is usually better to return a job ID after acceptance and emit completion/failure events, or use an asynchronous API with an explicit contract.

## 7. Distinguishing Spring Framework and Spring Integration

Do not confuse APIs between the two modules:

- **Spring Framework – `spring-messaging`:** provides `Message`, `MessageChannel`, `MessageHandler`, `GenericMessagingTemplate`, and the `send` and `sendAndReceive` operations.
- **Spring Integration – `spring-integration-core`:** adds gateways and endpoints for building integration flows. Annotations such as `@MessagingGateway`, `@Gateway`, and `@ServiceActivator` belong to Spring Integration.

Example of a Spring Integration gateway:

```java
@MessagingGateway(defaultRequestChannel = "orders")
public interface OrderGateway {

    // One-way: does not require the gateway to return a business result.
    void publish(OrderCreated event);

    // Request-reply: caller receives OrderStatus from the downstream flow.
    OrderStatus findStatus(OrderQuery query);
}
```

This example requires the Spring Integration dependency and corresponding gateway/channel configuration. It is not part of the `spring-messaging` module alone.

In Spring Framework WebSocket/STOMP applications, `SimpMessagingTemplate.convertAndSend(destination, payload)` is a common way to push messages to a destination or subscribers. That call does not wait for each client to send back a business result. If a response to a client message is needed, it can be handled with `@MessageMapping` and routed using `@SendTo` or the corresponding reply mechanism.

## 8. Common Mistakes

1. **Treating `send() == true` as successful business processing.** This value only indicates that the channel accepted the message according to its contract.
2. **Assuming one-way is always asynchronous.** A channel may invoke the handler directly on the sending thread.
3. **Calling `sendAndReceive` when the handler does not send a reply.** The caller will receive `null` after timeout or wait indefinitely if no timeout is configured.
4. **Sending the reply to the wrong channel.** The reply never reaches the temporary reply channel, causing the request to time out.
5. **Not handling `null`.** Timeouts or missing replies are valid API outcomes.
6. **Confusing send timeout with receive timeout.** One bounds sending; the other bounds waiting for a reply.
7. **Using a shared reply channel across multiple requests without correlation.** Replies can be misrouted to the wrong request.
8. **Using a `void` method while expecting a return value.** A one-way contract does not provide a reply payload to the caller.

## 9. Implementation Checklist

- Clarify whether the sender needs a business outcome or only needs to emit a message.
- Choose a channel and transport with matching synchronous, asynchronous, persistence, and reliability characteristics.
- For request-reply, specify the reply channel and how replies are correlated with requests.
- Set send timeouts and receive timeouts appropriate to your SLA.
- Handle `null`, send failures, handler errors, and late-arriving replies.
- For retryable events, design idempotency and duplicate-message handling.
- Avoid synchronous request-reply for long-running work when a job ID and status events can be used instead.

## 10. References

- [Spring Framework – MessageChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Spring Framework – GenericMessagingTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html)
- [Spring Framework – ExecutorSubscribableChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [Spring Framework – Sending Messages over WebSocket/STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
- [Spring Integration – Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)
