# Copying Messages When Changing Data or Headers in Spring Messaging

In Spring Messaging, a message consists of a **payload** (primary data) and **headers** (accompanying metadata). When you need to change the payload or a header, the safe approach is to create a new message based on the old message. Spring provides `MessageBuilder` and `MessageHeaderAccessor` to do that.

This content focuses on the `spring-messaging` module of Spring Framework. Examples use Java 17+ and Spring Framework 7.0.10.

## 1. Why Create a New Message?

`Message<T>` provides two read operations: `getPayload()` and `getHeaders()`. `MessageHeaders` is an immutable map: calling `put()`, `putAll()`, `remove()`, or `clear()` on this map will throw `UnsupportedOperationException`.

The following example is not a valid way to update a header:

```java
message.getHeaders().put("priority", 5); // UnsupportedOperationException
```

Instead, create a new message using a builder. The original message continues to preserve its payload and headers; the new message contains the desired changes.

Two levels of immutability should be distinguished:

- **Message envelope and headers map:** Spring provides them as immutable once created.
- **Payload object and header values:** these objects can still be mutable. Spring does not automatically deep-copy a DTO, list, or map inside a message.

Therefore, creating a new message does not mean every object inside it has been deep-copied.

## 2. Choosing the Right Copy Approach

| Need | How to create the message | Result |
| --- | --- | --- |
| Keep payload, change or add headers | `MessageBuilder.fromMessage(source)` | Builder starts with the source message's payload and headers |
| Replace payload, keep metadata | `MessageBuilder.withPayload(newPayload).copyHeaders(source.getHeaders())` | New payload, copied headers |
| Only add missing headers | `copyHeadersIfAbsent(...)` | Values already in the builder are preserved |
| Remove a header | `removeHeader(name)` | The header is excluded from the new message |
| Remove a group of headers | `removeHeaders(patterns...)` | Matching headers are excluded from the new message |

### Keeping payload and changing headers

Use `fromMessage` when the payload is still right and only metadata needs to change:

```java
Message<Order> updated = MessageBuilder
        .fromMessage(original)
        .setHeader("priority", 5)
        .setHeader("processedBy", "billing")
        .build();
```

`fromMessage` creates a builder for a new message, copying the payload and headers from the source message. Subsequent `setHeader` calls modify the new build; they do not update the original message.

### Replacing payload while keeping headers

When the payload type or content changes, create a builder from the new payload and copy the headers:

```java
Message<OrderValidated> updated = MessageBuilder
        .withPayload(new OrderValidated("ORD-42", true))
        .copyHeaders(original.getHeaders())
        .build();
```

This is useful when a processing step transforms an input DTO into an output DTO while still needing to retain the trace ID, tenant ID, or business metadata.

### Replacing payload and adjusting metadata

You can chain operations on the same builder:

```java
Message<OrderValidated> updated = MessageBuilder
        .withPayload(new OrderValidated("ORD-42", true))
        .copyHeaders(original.getHeaders())
        .setHeader("stage", "validation")
        .removeHeader("temporaryFlag")
        .build();
```

Operation order matters when a header appears multiple times. `copyHeaders` overwrites a value with the same name already in the builder; `copyHeadersIfAbsent` only populates a value if the builder does not yet have that header.

For example, if you want to prioritize a default value for the current step:

```java
Message<?> updated = MessageBuilder
        .withPayload(newPayload)
        .setHeader("source", "local")
        .copyHeadersIfAbsent(original.getHeaders())
        .build();
```

If the source message has `source=checkout`, the new message still keeps `source=local`, because the header was already set before copying.

### Removing headers

You can use `removeHeader` or set a `null` value:

```java
Message<?> withoutPriority = MessageBuilder
        .fromMessage(original)
        .removeHeader("priority")
        .build();

Message<?> withoutTemporaryFlag = MessageBuilder
        .fromMessage(original)
        .setHeader("temporaryFlag", null)
        .build();
```

`setHeader(name, null)` means removing the header, not storing a null value. `removeHeaders` supports name patterns such as `trace*`, `*Token`, or `*internal*`; use patterns narrow enough to avoid deleting essential metadata.

## 3. Complete Java Example

The following example demonstrates five scenarios: changing a header, replacing the payload while keeping headers, copying only missing headers, removing a header, and using `MessageHeaderAccessor`. The payload is a Java record so the demonstration data is immutable.

Create the file `src/main/java/MessageCopyDemo.java`:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.support.MessageHeaderAccessor;

public class MessageCopyDemo {

    private record OrderPayload(String orderId, String status) {}

    public static void main(String[] args) {
        Message<OrderPayload> original = MessageBuilder
                .withPayload(new OrderPayload("ORD-42", "CREATED"))
                .setHeader("traceId", "trace-42")
                .setHeader("priority", 3)
                .setHeader("source", "checkout")
                .build();

        // Keep payload, change priority, and add processedBy.
        Message<OrderPayload> headerChanged = MessageBuilder
                .fromMessage(original)
                .setHeader("priority", 5)
                .setHeader("processedBy", "billing")
                .build();

        // Create new payload, copy metadata, then add stage.
        Message<OrderPayload> payloadChanged = MessageBuilder
                .withPayload(new OrderPayload(
                        original.getPayload().orderId(), "VALIDATED"))
                .copyHeaders(original.getHeaders())
                .setHeader("stage", "validation")
                .build();

        // source=local takes precedence; only copy missing headers.
        Message<OrderPayload> localDefaults = MessageBuilder
                .withPayload(original.getPayload())
                .setHeader("source", "local")
                .copyHeadersIfAbsent(original.getHeaders())
                .build();

        // Remove priority from the new message.
        Message<OrderPayload> stripped = MessageBuilder
                .fromMessage(original)
                .removeHeader("priority")
                .build();

        // Use a mutable accessor to edit headers, then create a new message.
        MessageHeaderAccessor accessor =
                MessageHeaderAccessor.getMutableAccessor(original);
        accessor.setHeader("auditedBy", "audit-service");

        Message<OrderPayload> accessorCopy = MessageBuilder
                .withPayload(original.getPayload())
                .setHeaders(accessor)
                .build();

        System.out.println("original status: " + original.getPayload().status());
        System.out.println("original priority: " + original.getHeaders().get("priority"));
        System.out.println("headerChanged status: " + headerChanged.getPayload().status());
        System.out.println("headerChanged priority: "
                + headerChanged.getHeaders().get("priority"));
        System.out.println("headerChanged processedBy: "
                + headerChanged.getHeaders().get("processedBy"));
        System.out.println("payloadChanged status: "
                + payloadChanged.getPayload().status());
        System.out.println("payloadChanged traceId: "
                + payloadChanged.getHeaders().get("traceId"));
        System.out.println("localDefaults source: "
                + localDefaults.getHeaders().get("source"));
        System.out.println("stripped priority: "
                + stripped.getHeaders().get("priority"));
        System.out.println("accessorCopy auditedBy: "
                + accessorCopy.getHeaders().get("auditedBy"));
        System.out.println("original priority after copies: "
                + original.getHeaders().get("priority"));
        System.out.println("same payload reference after fromMessage: "
                + (original.getPayload() == headerChanged.getPayload()));
    }
}
```

Create `pom.xml` at the root directory of the Maven project:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>message-copy-demo</artifactId>
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
                    <mainClass>MessageCopyDemo</mainClass>
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
original status: CREATED
original priority: 3
headerChanged status: CREATED
headerChanged priority: 5
headerChanged processedBy: billing
payloadChanged status: VALIDATED
payloadChanged traceId: trace-42
localDefaults source: local
stripped priority: null
accessorCopy auditedBy: audit-service
original priority after copies: 3
same payload reference after fromMessage: true
```

The last line shows that `fromMessage` keeps the same payload reference. In the example, the payload is a record, so its state cannot be mutated in place. If the payload were an `ArrayList`, `HashMap`, or mutable DTO, both messages could point to the same object and observe each other's changes.

## 4. Using MessageHeaderAccessor When Fine-Grained Header Control Is Needed

`MessageHeaderAccessor` is a helper class for reading and modifying headers in a controlled manner. It is useful when you need to access headers with specific types or work with specialized accessors such as `NativeMessageHeaderAccessor` and protocol accessors.

`MessageHeaderAccessor.getMutableAccessor(message)` creates an accessor capable of modifying a message's headers. After updating, you can pass the accessor to `MessageBuilder.setHeaders(accessor)` to build a new message:

```java
MessageHeaderAccessor accessor =
        MessageHeaderAccessor.getMutableAccessor(original);

accessor.setHeader("processedBy", "billing");

Message<?> updated = MessageBuilder
        .withPayload(original.getPayload())
        .setHeaders(accessor)
        .build();
```

By default, when calling `getMessageHeaders()`, the accessor locks further modifications and returns immutable headers. `setLeaveMutable(true)` allows continuing to edit headers after obtaining `MessageHeaders`, but should only be used during message initialization on the same thread. When finished, call `setImmutable()` before passing the message to another component or thread.

For ordinary cases, `MessageBuilder.fromMessage` and `withPayload(...).copyHeaders(...)` are usually easier to read and less stateful. Use an accessor when you need its specific capabilities, especially when you want to preserve a protocol-specific accessor type.

## 5. ID, Timestamp, and Correlation ID

A message has system headers such as `MessageHeaders.ID` and `MessageHeaders.TIMESTAMP`.

- `ID` is a UUID identifying a message instance. Spring generates the ID automatically; you should not manually set this value in headers.
- `TIMESTAMP` is managed by Spring's header creation mechanism. Manually copying headers does not overwrite these read-only system values.
- `copyHeaders` and `copyHeadersIfAbsent` do not overwrite `id` or `timestamp`.

When creating a new message from an old message, treat it as a new message instance. If you need to link multiple messages within the same business flow, use a dedicated header such as `correlationId`, `traceId`, or `businessRequestId`. For example, the first message and the post-validation message can have different IDs while both retaining `traceId=trace-42`.

Do not use `MessageHeaders.ID` as a business correlation ID. The ID identifies a message; a correlation ID links related messages together.

## 6. Copying Headers Is Not a Deep Copy

The `fromMessage`, `copyHeaders`, and `copyHeadersIfAbsent` methods copy the name-value pairs of headers. This copying does not automatically deep-clone referenced objects.

For example, if a header contains a mutable list:

```java
List<String> tags = new ArrayList<>(List.of("priority"));
Message<?> source = MessageBuilder
        .withPayload("order")
        .setHeader("tags", tags)
        .build();

Message<?> copy = MessageBuilder
        .fromMessage(source)
        .build();
```

The header maps of `source` and `copy` are two separate message header sets, yet the `tags` value can still be the exact same list object. Modifying that list can affect both messages. If data isolation is needed, make a copy of the list or header object before attaching it to the builder.

The same applies to the payload. If the payload is mutable and a downstream step needs to change its content, create a new DTO or a defensive copy instead of mutating a payload shared across components.

## 7. Be Careful When Copying All Headers

`copyHeaders(original.getHeaders())` is convenient, yet it copies every copyable header. Some headers carry routing or protocol context, for example:

- `contentType`: may no longer be accurate if the payload changes format.
- `replyChannel` and `errorChannel`: may no longer be appropriate if the message moves to a different flow.
- Broker-, WebSocket/STOMP-, or adapter-specific headers: may only make sense in the source context.
- Temporary headers used in a single processing step: probably should not be forwarded to the next step.

When creating a message for a new destination or payload, check which headers remain valid. If only a few pieces of metadata are needed, copy selectively:

```java
Message<?> outbound = MessageBuilder
        .withPayload(newPayload)
        .setHeader("traceId", original.getHeaders().get("traceId"))
        .setHeader("tenantId", original.getHeaders().get("tenantId"))
        .setHeader("contentType", "application/json")
        .build();
```

This example keeps the two needed headers and resets the content type to match the new payload. In real applications, declare custom header names as constants to avoid typos between producer and consumer.

## 8. Common Mistakes

1. **Calling `put` or `remove` directly on `MessageHeaders`.** The headers map is immutable; use a builder or accessor.
2. **Using `fromMessage` and assuming the payload was cloned.** The builder still uses the old payload reference.
3. **Using `withPayload(newPayload)` and forgetting to copy necessary metadata.** Trace ID or tenant ID may be lost.
4. **Calling `copyHeaders` after setting preferred values.** Source headers will overwrite headers with the same name in the builder. To keep existing values, use `copyHeadersIfAbsent`.
5. **Copying all headers to another flow.** This may carry over stale content types, reply channels, or protocol metadata.
6. **Trying to overwrite ID or timestamp.** These are read-only system headers.
7. **Using the message ID as an end-to-end business ID.** Creating a new message can generate a new ID; use a separate correlation ID.
8. **Sharing mutable payloads or header values across multiple messages.** Mutating one object can affect other messages referencing it.

## 9. Checklist Before Sending a New Message

- Determine whether you need to change the payload, headers, or both.
- Use `fromMessage` when keeping the payload; use `withPayload` when replacing the payload.
- Use `copyHeaders` to prioritize source metadata; use `copyHeadersIfAbsent` to preserve values already set in the builder.
- Remove or update content type, reply/error channels, and protocol metadata if they are no longer accurate.
- Preserve correlation ID or trace ID using dedicated business headers.
- Defensively copy mutable payloads and header values if data isolation is required.
- Build the complete message before sending it to another channel or thread.

## 10. References

- [Spring Framework – MessageBuilder Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework – MessageHeaders Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework – MessageHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- [Spring Framework – Message Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html)
