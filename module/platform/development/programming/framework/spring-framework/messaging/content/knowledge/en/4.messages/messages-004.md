# Creating Messages with MessageBuilder.withPayload and MessageBuilder.fromMessage

## 1. A Message Consists of Payload and Headers

In Spring Messaging, `Message<T>` is the unit of data exchanged between components. A message has two parts:

- **Payload**: the main content, of type `T`, such as a string, DTO, business command, or domain object.
- **Headers**: accompanying metadata, such as `contentType`, `correlationId`, `replyChannel`, `errorChannel`, or custom headers.

The `Message<T>` interface provides `getPayload()` and `getHeaders()`. It has no setters to replace the payload or edit headers in place. Spring provides `MessageBuilder<T>` to create a message and prepare its headers before calling `build()`.

The two commonly used factory methods are:

| Method | Payload of resulting message | Initial headers |
| --- | --- | --- |
| `MessageBuilder.withPayload(payload)` | The passed-in payload | Starts with a fresh set of headers |
| `MessageBuilder.fromMessage(message)` | Keeps the source message's payload | Copies headers from the source message |

Both return `MessageBuilder<T>`, allowing you to chain multiple operations and then call `build()` to obtain a `Message<T>`.

## 2. Creating a New Message with withPayload

`withPayload(T payload)` initializes a builder for a new message with the given payload. This is the right choice when data originates from a new source or when you want to replace the payload with a different value.

~~~java
Message<String> message = MessageBuilder
    .withPayload("order-42")
    .setHeader("eventType", "order.created")
    .setHeader("correlationId", "req-17")
    .build();
~~~

The result has payload `"order-42"` and two custom headers. `withPayload` does not accept `null`; a payload must exist to create a message.

The generic type is inferred from the payload. For example:

~~~java
record OrderCreated(long orderId, String customerId) {
}

Message<OrderCreated> event = MessageBuilder
    .withPayload(new OrderCreated(42L, "customer-7"))
    .setHeader("eventType", "order.created")
    .build();
~~~

In this case, the `event` variable has type `Message<OrderCreated>`. Consumers can receive the properly typed payload without casting from `Object`.

If the payload is a `Throwable` object, Spring creates an `ErrorMessage` instead of a `GenericMessage`. This is how error messages are represented in Spring Messaging.

## 3. Creating a Builder from an Existing Message with fromMessage

`fromMessage(Message<T> message)` creates a builder from a source message. The payload and headers of the source message are populated into the builder, making it possible to add or adjust metadata without rebuilding each header individually.

~~~java
Message<String> original = MessageBuilder
    .withPayload("order-42")
    .setHeader("eventType", "order.created")
    .setHeader("correlationId", "req-17")
    .build();

Message<String> validated = MessageBuilder
    .fromMessage(original)
    .setHeader("eventType", "order.validated")
    .setHeader("processingStage", "validation")
    .build();
~~~

The `validated` message retains the payload `"order-42"` and the `correlationId` header of the original message. The `eventType` header is updated to `order.validated`; a new header `processingStage` is added.

This is useful when a component receives a message, validates or enriches metadata, and then forwards it to the next component. The builder creates a message with the prepared headers; the source message is not modified directly.

`fromMessage` preserves the payload type `T`. If the source is `Message<String>`, the builder produces a message with a `String` payload. When you need to change the payload to a different type, use `withPayload(newPayload)` and copy the necessary headers from the source message.

If the input is an `ErrorMessage`, `fromMessage` also forwards the `originalMessage` attached to the error message to the newly created error message.

## 4. Adjusting Headers in the Builder

Header methods return the builder itself, so they can be chained in a readable order:

| Method | Behavior |
| --- | --- |
| `setHeader(name, value)` | Sets or replaces the header value. If `value` is `null`, that header is removed. |
| `setHeaderIfAbsent(name, value)` | Sets the value only if the header does not already exist. |
| `copyHeaders(map)` | Copies name/value pairs and overwrites existing headers with the same name. |
| `copyHeadersIfAbsent(map)` | Copies only headers not yet present, without overwriting existing values. |
| `removeHeader(name)` | Removes a header by name. |
| `removeHeaders(patterns...)` | Removes headers matching the passed-in name patterns. |

Example using `setHeaderIfAbsent`:

~~~java
Message<String> message = MessageBuilder
    .withPayload("order-43")
    .setHeader("source", "checkout")
    .setHeaderIfAbsent("source", "fallback")
    .build();
~~~

The `source` header keeps the value `checkout`, because it was already set before calling `setHeaderIfAbsent`.

### 4.1. copyHeaders and copyHeadersIfAbsent

These two methods are especially useful when combining `withPayload` with headers from an old message:

~~~java
Message<String> original = MessageBuilder
    .withPayload("order-42")
    .setHeader("eventType", "order.created")
    .setHeader("correlationId", "req-17")
    .build();

Message<String> transformed = MessageBuilder
    .withPayload("Order order-42 has been created")
    .copyHeaders(original.getHeaders())
    .setHeader("representation", "text")
    .build();
~~~

The new payload is a descriptive string, while business headers such as `eventType` and `correlationId` are preserved. Then the builder adds the `representation` header.

The order of method calls affects the result:

~~~java
Message<String> keepLocalValue = MessageBuilder
    .withPayload("order-44")
    .setHeader("eventType", "local.event")
    .copyHeadersIfAbsent(original.getHeaders())
    .build();
~~~

If the source message also has `eventType`, the value `local.event` is kept because `copyHeadersIfAbsent` does not overwrite an already existing header.

Conversely, `copyHeaders` overwrites regular header values set earlier. If you want the builder's own value to win, call `copyHeaders` first and then call `setHeader`.

## 5. Immutability and System Headers

### 5.1. Do not modify MessageHeaders directly

`MessageHeaders` is an immutable structure. Operations like `put`, `putAll`, `remove`, or `clear` will throw `UnsupportedOperationException`.

The following code is invalid:

~~~java
message.getHeaders().put("status", "validated");
~~~

Create a new message via the builder instead:

~~~java
Message<String> updated = MessageBuilder
    .fromMessage(message)
    .setHeader("status", "validated")
    .build();
~~~

After calling `build()`, the headers of the message created under the default mechanism are immutable. Do not use a builder expecting to modify the headers of a message that has already been sent.

### 5.2. An immutable message does not mean the payload is deep-copied

Spring protects the message structure and the headers map, but does not automatically deep-copy the payload or every object stored in a header. If the payload is an `ArrayList` or a header contains a mutable object, messages created from the same reference can still see changes made to that object.

Therefore:
- Prefer payloads that are records, value objects, or immutable structures.
- Avoid placing shared mutable collections into headers.
- If data must be transformed, create a new payload and then build a new message.

### 5.3. ID and timestamp are framework-managed headers

`MessageHeaders.ID` and `MessageHeaders.TIMESTAMP` are system headers. The default ID is auto-generated; do not set business IDs or timestamps with `setHeader` or try to overwrite them via `copyHeaders`.

If you need to link multiple messages in the same processing flow, create dedicated business headers such as `correlationId`, `traceId`, or `causationId`. These values are managed by the application and have clear business meaning.

## 6. Complete Runnable Example with Java 17+

The following example illustrates three scenarios:

1. `withPayload` creates the initial message.
2. `fromMessage` keeps the payload, inherits headers, and adds processing information.
3. `withPayload` creates a new payload and `copyHeaders` carries metadata over from the source message.

Project structure:

~~~text
message-builder-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── MessageBuilderDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>message-builder-demo</artifactId>
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
                    <mainClass>MessageBuilderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/MessageBuilderDemo.java**

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class MessageBuilderDemo {

    public static void main(String[] args) {
        Message<String> original = MessageBuilder
            .withPayload("order-42")
            .setHeader("eventType", "order.created")
            .setHeader("correlationId", "req-17")
            .build();

        Message<String> validated = MessageBuilder
            .fromMessage(original)
            .setHeader("eventType", "order.validated")
            .setHeader("processingStage", "validation")
            .build();

        Message<String> description = MessageBuilder
            .withPayload("Order order-42 has been created")
            .copyHeaders(original.getHeaders())
            .setHeader("representation", "text")
            .build();

        Message<String> localEvent = MessageBuilder
            .withPayload("order-44")
            .setHeader("eventType", "local.event")
            .copyHeadersIfAbsent(original.getHeaders())
            .build();

        System.out.println("original.payload=" + original.getPayload());
        System.out.println("validated.payload=" + validated.getPayload());
        System.out.println("validated.eventType="
            + validated.getHeaders().get("eventType"));
        System.out.println("validated.correlationId="
            + validated.getHeaders().get("correlationId"));
        System.out.println("validated.processingStage="
            + validated.getHeaders().get("processingStage"));
        System.out.println("original.processingStage="
            + original.getHeaders().get("processingStage"));
        System.out.println("description.payload=" + description.getPayload());
        System.out.println("description.eventType="
            + description.getHeaders().get("eventType"));
        System.out.println("description.representation="
            + description.getHeaders().get("representation"));
        System.out.println("localEvent.eventType="
            + localEvent.getHeaders().get("eventType"));
    }
}
~~~

Run the following command in the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

Stdout output:

~~~text
original.payload=order-42
validated.payload=order-42
validated.eventType=order.validated
validated.correlationId=req-17
validated.processingStage=validation
original.processingStage=null
description.payload=Order order-42 has been created
description.eventType=order.created
description.representation=text
localEvent.eventType=local.event
~~~

The output shows:
- `validated` keeps the payload and correlation ID from the source message, while having its own header for the processing step.
- `original.processingStage` remains `null`; the builder does not add headers to the source message.
- `description` has a new payload while still carrying the headers copied from `original`.
- `localEvent.eventType` keeps `local.event` because `copyHeadersIfAbsent` does not overwrite an existing header.

## 7. When to Choose Each Factory Method?

| Need | How to write it |
| --- | --- |
| Create a message from new data | `MessageBuilder.withPayload(payload).build()` |
| Create a message and add metadata | `withPayload(payload).setHeader(...).build()` |
| Keep the payload, add or modify headers | `MessageBuilder.fromMessage(source).setHeader(...).build()` |
| Change the payload while keeping metadata | `MessageBuilder.withPayload(newPayload).copyHeaders(source.getHeaders()).build()` |
| Accept only headers not yet present in the builder | `withPayload(payload).copyHeadersIfAbsent(source.getHeaders()).build()` |
| Remove a header before forwarding | `MessageBuilder.fromMessage(source).removeHeader("internalNote").build()` |

Do not use `fromMessage` to replace the payload; that method takes the payload from the source message. Also do not modify the map returned from `getHeaders()`; create a new message using a builder instead.

In the Spring Framework 7.0.10 implementation, if the builder from `fromMessage` has not been modified, `build()` may return the source message itself as an optimization. If the builder has changed headers, `build()` creates a message matching the prepared payload and headers. Do not use object identity comparison to infer business meaning; check the required payload and headers.

## 8. Common Mistakes

| Mistake | Why it happens | How to fix |
| --- | --- | --- |
| Calling `message.getHeaders().put(...)` | `MessageHeaders` is immutable | Use `MessageBuilder.fromMessage(message).setHeader(...).build()` |
| Using `fromMessage` while expecting a new payload | `fromMessage` keeps the source payload | Use `withPayload(newPayload)` |
| Header overwritten unexpectedly | `copyHeaders` overwrites existing values | Change call order or use `copyHeadersIfAbsent` |
| Calling `setHeader(name, null)` to store a null value | A null value means deleting the header | Use an explicit representation value if business logic needs an empty state |
| Trying to set `id` or `timestamp` arbitrarily | These are Spring-managed system headers | Use `correlationId` or a dedicated business header |
| Assuming the payload is cloned when calling `fromMessage` | The builder reuses the payload reference | Create an immutable payload or create a new object when transformation is needed |
| Sharing mutable header values | Copying headers does not deep-clone individual values | Prefer immutable value objects and unmodifiable collections |

## 9. Usage Checklist

- [ ] Choose `withPayload` when starting from a new payload.
- [ ] Choose `fromMessage` when you want to keep the payload and inherit headers.
- [ ] Use `withPayload(newPayload).copyHeaders(source.getHeaders())` when you need to replace the payload while keeping metadata.
- [ ] Clearly determine the order between `setHeader`, `copyHeaders`, and `copyHeadersIfAbsent`.
- [ ] Use dedicated business headers for correlation and tracing.
- [ ] Do not modify `MessageHeaders` directly.
- [ ] Avoid sharing payloads or header values that can be mutated.
- [ ] Inspect both payload and headers after calling `build()`.

## 10. References

- [Spring Framework API — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework API — Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html)
- [Spring Framework API — MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework API — MessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- [Spring Framework API — GenericMessage](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/GenericMessage.html)
