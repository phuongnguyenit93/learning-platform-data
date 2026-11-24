# MessageRequestReplyOperations and Request-Reply Exchange in Spring Messaging

In Spring Messaging, request-reply is a pattern where one component sends a request to a destination and waits for a corresponding response. The `MessageRequestReplyOperations<D>` interface describes this contract: sending a request message and receiving a reply message, or converting request/reply payloads via a `MessageConverter`.

This interface belongs to the `org.springframework.messaging.core` package. It is an **operation contract**, not a specific channel or transport. An implementation such as `GenericMessagingTemplate` can use a `MessageChannel`; another specialized template can work with a transport's destination such as JMS.

## 1. What Is MessageRequestReplyOperations?

Abbreviated declaration:

```java
public interface MessageRequestReplyOperations<D> {
    Message<?> sendAndReceive(Message<?> requestMessage);

    Message<?> sendAndReceive(D destination, Message<?> requestMessage);

    <T> T convertSendAndReceive(Object request, Class<T> targetClass);

    <T> T convertSendAndReceive(D destination,
                               Object request,
                               Class<T> targetClass);
}
```

This is the core part of the API; the interface also has overloads for passing headers and a `MessagePostProcessor`.

The type parameter `D` represents the destination type used by the implementation. For example:

- With `GenericMessagingTemplate`, the destination is a `MessageChannel`.
- With a JMS integration template, the destination can be a JMS `Destination` object.
- With `DestinationResolvingMessageRequestReplyOperations`, there are additional overloads accepting a `String` destination name for the implementation to resolve into an actual destination.

Do not instantiate the interface directly. In Spring Messaging applications, you typically use `GenericMessagingTemplate` and reference it through the interface so code depends on the request-reply contract:

```java
GenericMessagingTemplate template = new GenericMessagingTemplate();
MessageRequestReplyOperations<MessageChannel> operations = template;
```

This style of declaration keeps the caller decoupled from the concrete implementation class beyond the chosen destination type.

## 2. Two Main Groups of Methods

### `sendAndReceive`: Sending and Receiving Messages

`sendAndReceive` takes an already-created `Message<?>` and returns the reply also as a `Message<?>`:

```java
Message<?> reply = operations.sendAndReceive(destination, requestMessage);
```

Use this API when you need control over the request's payload and headers, or when you need to read the response's headers such as correlation ID, content type, or metadata returned by the handler.

There are two forms:

- `sendAndReceive(requestMessage)`: sends to the default destination configured on the template.
- `sendAndReceive(destination, requestMessage)`: specifies the destination explicitly for the call.

### `convertSendAndReceive`: Converting Request and Reply Payloads

`convertSendAndReceive` takes a plain payload object, wraps/converts it into a message, sends it, receives the reply, and converts the reply payload to the target type:

```java
String reply = operations.convertSendAndReceive(
        destination,
        "Lan",
        String.class);
```

The overloads allow:

- Passing headers as a `Map<String, Object>`.
- Passing a `MessagePostProcessor` to modify the request message after it is created/converted.
- Combining both headers and a post-processor.
- Using the default destination or passing an explicit destination.

| Method | Request | Result |
| --- | --- | --- |
| `sendAndReceive` | `Message<?>` | Raw reply `Message<?>` |
| `convertSendAndReceive` | Any payload | Reply payload converted to `Class<T>` |
| With `headers` | Payload + metadata | Headers are attached to the request |
| With `MessagePostProcessor` | Created request message | Allows adding/modifying the message before sending |

`MessagePostProcessor` applies to the request message. It is useful for adding a correlation ID, version, tenant, or metadata without manually building the entire message from scratch.

## 3. Request-Reply Flow

With a `MessageChannel`-based implementation, the exchange flow typically proceeds as follows:

1. The caller creates the request.
2. The template prepares a reply-receiving mechanism for the call and sends the request to the destination.
3. The handler receives the request and processes the payload.
4. The handler sends the reply back to the reply destination/channel provided by the template in the message.
5. The template receives the reply and returns it to the caller.
6. If no reply is received within the receive timeout, the method returns `null`.

In `GenericMessagingTemplate`, the template manages a temporary reply channel for request-reply. The handler can retrieve that channel from the `MessageHeaders.REPLY_CHANNEL` header and send the response back. Each call has its own receiving channel, so replies can be matched to the right caller when multiple requests are waiting concurrently.

The `MessageRequestReplyOperations` interface does not require the handler to return a Java value from `handleMessage`. The handler must send a reply message according to the transport/template mechanism. If the handler only processes the request without sending a reply, the caller will keep waiting until timeout.

## 4. Java 17+ Example with GenericMessagingTemplate

The example uses `ExecutorSubscribableChannel` to receive requests and send replies. It demonstrates `sendAndReceive`, `convertSendAndReceive`, headers, a post-processor, and the timeout case.

Create the file `src/main/java/RequestReplyOperationsDemo.java`:

```java
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.core.GenericMessagingTemplate;
import org.springframework.messaging.core.MessageRequestReplyOperations;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class RequestReplyOperationsDemo {

    public static void main(String[] args) {
        ExecutorSubscribableChannel requests = new ExecutorSubscribableChannel();

        requests.subscribe(request -> {
            if ("no-reply".equals(request.getPayload())) {
                return;
            }

            String name = (String) request.getPayload();
            Object version = request.getHeaders().get("requestVersion");
            String greeting = version == null
                    ? "Hello, " + name
                    : "v" + version + ": Hello, " + name;

            Object target = request.getHeaders().get(MessageHeaders.REPLY_CHANNEL);
            if (target instanceof MessageChannel replyChannel) {
                replyChannel.send(MessageBuilder
                        .withPayload(greeting)
                        .setHeader("correlationId",
                                request.getHeaders().get("correlationId"))
                        .build());
            }
        });

        GenericMessagingTemplate template = new GenericMessagingTemplate();
        template.setReceiveTimeout(200);

        MessageRequestReplyOperations<MessageChannel> operations = template;

        // API preserving the request Message and reply Message.
        Message<String> request = MessageBuilder
                .withPayload("Lan")
                .setHeader("correlationId", "req-42")
                .build();

        Message<?> reply = operations.sendAndReceive(requests, request);

        // API converting payloads and applying a post-processor to the request.
        String converted = operations.convertSendAndReceive(
                requests,
                "Minh",
                Map.of("correlationId", "req-43"),
                String.class,
                message -> MessageBuilder.fromMessage(message)
                        .setHeader("requestVersion", 1)
                        .build());

        // Handler intentionally does not reply; the template reaches receive timeout and returns null.
        String noReply = operations.convertSendAndReceive(
                requests, "no-reply", String.class);

        System.out.println("reply payload: "
                + (reply == null ? "<timeout>" : reply.getPayload()));
        System.out.println("reply correlationId: "
                + (reply == null ? null : reply.getHeaders().get("correlationId")));
        System.out.println("converted reply with post-processor: " + converted);
        System.out.println("no reply result: " + noReply);
    }
}
```

Create `pom.xml` in the root directory of the Maven project:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>request-reply-operations-demo</artifactId>
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
                    <mainClass>RequestReplyOperationsDemo</mainClass>
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

Stdout output:

```text
reply payload: Hello, Lan
reply correlationId: req-42
converted reply with post-processor: v1: Hello, Minh
no reply result: null
```

In the example:

- The first call uses `sendAndReceive`, so the caller receives the full reply message and can read the `correlationId` header.
- The second call uses `convertSendAndReceive`; the `String` payload is converted through the message converter. The `requestVersion` header is added by the post-processor and the handler uses it to construct the reply content.
- The last call receives no reply. With a 200 ms receive timeout, the result is `null`.

## 5. Configuring Timeouts and Handling Errors

`MessageRequestReplyOperations` describes request-reply operations, but does not declare timeout parameters on each method. Timeouts are configured by the concrete implementation.

With `GenericMessagingTemplate`:

```java
GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setSendTimeout(500);
template.setReceiveTimeout(2_000);
```

Both values are in milliseconds:

- **Send timeout:** time limit for waiting when sending the request to the destination/channel.
- **Receive timeout:** time limit for waiting for a reply after the request has been sent.

For request-reply, a finite receive timeout prevents the caller from waiting indefinitely if the handler fails to send a reply, the reply is lost, or the processing flow hits an error. Both `sendAndReceive` and `convertSendAndReceive` can return `null` when no reply is received, such as on timeout. Check for `null` before using the payload.

Operations can throw `MessagingException` or a subclass when messaging errors occur. Distinguish among:

- Failure to send the request.
- Handler failure while processing the request.
- No reply received before timeout.
- Reply arriving after the caller has timed out.

With `GenericMessagingTemplate`, late replies are logged at WARN level by default. You can enable `setThrowExceptionOnLateReply(true)` so the template throws `MessageDeliveryException` when the reply channel is no longer awaited by the caller.

Do not retry every error blindly. If the request may have already been processed before the response was lost, retrying can execute the business operation twice. Use a request ID/correlation ID for tracking and an idempotency key to protect side-effecting operations such as creating orders, charging payments, or updating state.

## 6. Headers, Correlation, and MessagePostProcessor

### Request Headers

The overloads with `Map<String, Object>` allow passing metadata:

```java
String reply = operations.convertSendAndReceive(
        requests,
        "Lan",
        Map.of(
                "correlationId", "req-100",
                "tenantId", "tenant-a"
        ),
        String.class);
```

Headers can be used for routing, authorization checks, data partitioning, or observability of the processing flow. Only pass headers that the destination and handler understand; do not copy all metadata from another message if it is no longer appropriate.

### MessagePostProcessor

The post-processor receives the created request message and returns the modified message:

```java
String reply = operations.convertSendAndReceive(
        requests,
        "Lan",
        String.class,
        message -> MessageBuilder.fromMessage(message)
                .setHeader("correlationId", "req-101")
                .setHeader("schemaVersion", 2)
                .build());
```

You can use it to standardize metadata, add a correlation ID, or apply per-call information. If you need to replace the payload, the post-processor can also build a new message with a new payload; however, preserve the payload type expected by the handler.

### Correlation ID and Message ID

`MessageHeaders.ID` identifies a single message instance. A correlation ID links a request with a reply or with multiple messages in the same business operation. These two concepts serve different purposes:

- The request ID and reply ID can be different.
- The reply should carry the correlation ID corresponding to the request if the transport/template does not manage correlation automatically in another way.
- Do not use the message ID as a business ID spanning multiple steps.
- With remote brokers, an adapter may map the correlation ID to a transport-specific property.

## 7. Destinations and Implementations

`MessageRequestReplyOperations<D>` does not lock the application to one type of destination. The type `D` and the implementation determine how the destination is located, how the request is sent, and how the reply is received.

| Implementation/Contract | Destination | Notes |
| --- | --- | --- |
| `GenericMessagingTemplate` | `MessageChannel` | Used for Spring Messaging channels |
| `DestinationResolvingMessageRequestReplyOperations` | `String` destination name | Adds the ability to resolve a name into a destination |
| `JmsMessagingTemplate` | JMS `Destination` or destination name | Integrates with JMS request-reply and JMS reply/correlation rules |

When using `GenericMessagingTemplate`, you can configure a default destination or pass a specific `MessageChannel` per call. If using destination names, the template needs a `DestinationResolver` or corresponding resolution mechanism.

With JMS, the template and provider handle reply-to/correlation details according to JMS rules. Do not assume the internal `MessageHeaders.REPLY_CHANNEL` header mechanism of `GenericMessagingTemplate` is identical to a broker's mechanism.

## 8. When Should You Use Request-Reply?

Request-reply is appropriate when the caller needs a result to decide how to proceed, for example:

- Looking up the status or details of an entity.
- Checking a business precondition before executing the next step.
- Asking a service to compute and return a result within a short time.
- Sending a command that needs an acknowledgment or structured result.

Do not keep the caller waiting for a job that takes several minutes. In that case, you should usually send a one-way command, receive a job ID, and track status via events or a query API. This avoids holding threads and connections for long periods.

Request-reply over messaging also does not automatically guarantee exactly-once processing. The system still needs to define timeouts, retries, duplicate handling, correlation, and recovery when the caller does not receive a response even though the handler finished.

## 9. Common Mistakes

1. **Instantiating `MessageRequestReplyOperations` directly.** It is an interface; use an implementation such as `GenericMessagingTemplate`.
2. **Confusing `sendAndReceive` with `convertSendAndReceive`.** One API returns the entire reply message; the other returns the payload converted to the target type.
3. **Forgetting that the handler must send a reply.** Simply having the handler receive the request does not automatically produce a response.
4. **Not configuring a receive timeout.** The caller may wait for a long time or indefinitely depending on the template.
5. **Not handling `null`.** Receiving no reply before timeout is an expected possible outcome.
6. **Setting correlation IDs incorrectly.** Responses can be hard to match to requests, especially when multiple requests are in flight concurrently.
7. **Using the wrong destination type `D`.** `GenericMessagingTemplate` works with `MessageChannel`; JMS templates use JMS destinations.
8. **Thinking MessagePostProcessor processes the reply.** It is applied to the request message before sending.
9. **Retrying without deduplication.** The request may have already been processed even if the caller did not receive the reply.

## 10. Implementation Checklist

- Choose the right implementation and destination type.
- Use `sendAndReceive` if you need both the reply payload and headers.
- Use `convertSendAndReceive` if you want request/reply payload conversion.
- Pass only necessary headers; set correlation IDs clearly.
- Use `MessagePostProcessor` for metadata that needs to be added after request conversion.
- Configure send timeout and receive timeout aligned with the SLA.
- Handle `null`, `MessagingException`, late replies, and handler errors.
- Design bounded retries and idempotency for commands with business side effects.
- Use one-way + job ID/status for long-running work.

## 11. References

- [Spring Framework – MessageRequestReplyOperations Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessageRequestReplyOperations.html)
- [Spring Framework – GenericMessagingTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html)
- [Spring Framework – DestinationResolvingMessageRequestReplyOperations Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/DestinationResolvingMessageRequestReplyOperations.html)
- [Spring Framework – MessagePostProcessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessagePostProcessor.html)
