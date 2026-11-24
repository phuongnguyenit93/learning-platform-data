# Testing MessageBuilder, Headers, and Data Converters

In Spring Messaging, a message does not contain only a payload. It also has headers carrying metadata such as content type, correlation ID, routing information, or processing data. As a message passes through multiple components, the payload may be converted between a Java object and its representation on the transport. Therefore, messaging tests need to verify the payload content, headers, and conversion results together.

Three core components to master:

- **MessageBuilder** creates a message from a payload and sets headers in a consistent way.
- **MessageHeaders** provides the message's metadata. The headers of an already-created message are immutable; to change them, you need to create a new message or use an appropriate accessor.
- **MessageConverter** converts the payload between a Java object and the data format used by the transport or endpoint. A header such as content type can affect how the converter chooses the format.

This lesson focuses on how to write unit tests for the components above, how to check for common errors, and how to distinguish message conversion from codecs in transports such as RSocket.

## 1. Structure of a Spring Message

Spring represents a message using the **Message<T>** interface, consisting of a payload and headers:

~~~java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
~~~

The payload is the primary data, such as **OrderCreatedEvent**, **String**, **byte[]**, or a DTO. Headers are a map containing accompanying metadata.

Example of creating a message:

~~~java
Message<String> message = MessageBuilder
    .withPayload("Order O-100 created")
    .setHeader("correlationId", "corr-100")
    .setHeader("source", "order-service")
    .build();
~~~

You can read the components:

~~~java
String payload = message.getPayload();
String correlationId = message.getHeaders().get(
    "correlationId",
    String.class
);
~~~

Do not cram all operational information into the payload if that information belongs to metadata. For example, correlation ID, content type, and certain routing attributes are usually more suitable for headers. Conversely, business data that needs to be processed by the consumer must reside in the payload or a clearly defined business schema.

### System Headers and Application Headers

**MessageHeaders** provides several standard headers:

- **MessageHeaders.ID**: message identifier managed by Spring.
- **MessageHeaders.TIMESTAMP**: message creation timestamp if timestamps are enabled.
- **MessageHeaders.CONTENT_TYPE**: MIME type describing the payload format.
- **MessageHeaders.REPLY_CHANNEL**: reply channel in request-reply flows.
- **MessageHeaders.ERROR_CHANNEL**: error-handling channel in mechanisms that support this header.

Applications can add custom headers such as **correlationId**, **tenantId**, or **eventVersion**. Header names should be centralized in constants to avoid typos and mismatches between producers and consumers.

~~~java
final class OrderHeaders {
    static final String CORRELATION_ID = "correlationId";
    static final String EVENT_VERSION = "eventVersion";

    private OrderHeaders() {
    }
}
~~~

Do not arbitrarily overwrite system headers such as ID or timestamp. Check each transport's contract before using header names that have special meaning.

## 2. Using MessageBuilder Properly

**MessageBuilder** helps create messages without having to implement **Message** yourself or manipulate the headers map directly.

### Creating a New Message

~~~java
Message<OrderCreatedEvent> message = MessageBuilder
    .withPayload(new OrderCreatedEvent("O-100", "CREATED"))
    .setHeader(OrderHeaders.CORRELATION_ID, "corr-100")
    .setHeader(OrderHeaders.EVENT_VERSION, 1)
    .build();
~~~

**withPayload** accepts the payload; **setHeader** adds or updates a header; **build** creates the complete message.

### Setting a Header Only When Absent

Use **setHeaderIfAbsent** when you want to preserve a previously provided value:

~~~java
Message<String> message = MessageBuilder
    .withPayload("ready")
    .setHeader("source", "gateway")
    .setHeaderIfAbsent("source", "fallback")
    .build();
~~~

In this example, the value of **source** remains **gateway**.

### Copying Headers

When creating a new message based on an existing message, you can use **fromMessage**:

~~~java
Message<String> original = MessageBuilder
    .withPayload("hello")
    .setHeader("correlationId", "corr-1")
    .build();

Message<String> copied = MessageBuilder
    .fromMessage(original)
    .setHeader("source", "worker")
    .build();
~~~

**copyHeaders** copies headers from a map and can overwrite existing values with the same name. **copyHeadersIfAbsent** only adds headers that do not already exist. Choose the right behavior to avoid accidentally changing the correlation ID or metadata supplied upstream.

### Removing Headers

You can remove a header when creating a new message:

~~~java
Message<String> sanitized = MessageBuilder
    .fromMessage(original)
    .removeHeader("internalDebug")
    .build();
~~~

**setHeader(name, null)** can also be used to remove a header in the builder. **removeHeader** expresses the intent more clearly and is easier to read when processing metadata.

## 3. MessageHeaders Are Immutable

Once a message is created, **MessageHeaders** does not allow modifying the map structure directly. This prevents components sharing the message from seeing a header changed unexpectedly.

Do not do the following:

~~~java
message.getHeaders().put("source", "worker");
~~~

This is invalid because headers are immutable and attempts to update the map will be rejected.

Create a new message instead:

~~~java
Message<String> updated = MessageBuilder
    .fromMessage(message)
    .setHeader("source", "worker")
    .build();
~~~

Keep in mind that immutability of the map does not automatically make every object stored inside a header immutable. If a header contains a **Map**, **List**, or mutable object, code holding a reference to that object can still mutate its internal state. It is best to use simple, immutable, strongly typed metadata values.

## 4. Testing MessageBuilder with JUnit 5

Unit tests should verify the payload, application-added headers, and behavior when copying or removing headers.

Suppose we have an event:

~~~java
public record OrderCreatedEvent(
    String orderId,
    String status
) {}
~~~

Test creating a message:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageBuilderTest {

    @Test
    void shouldBuildMessageWithPayloadAndHeaders() {
        OrderCreatedEvent event =
            new OrderCreatedEvent("O-100", "CREATED");

        Message<OrderCreatedEvent> message = MessageBuilder
            .withPayload(event)
            .setHeader("correlationId", "corr-100")
            .setHeader("eventVersion", 1)
            .build();

        assertSame(event, message.getPayload());
        assertEquals(
            "corr-100",
            message.getHeaders().get("correlationId")
        );
        assertEquals(
            1,
            message.getHeaders().get("eventVersion")
        );
        assertNotNull(message.getHeaders().getId());
    }
}
~~~

The test uses **assertSame** to confirm that the builder keeps the exact payload object passed in. If the system requires copying or serializing the payload, that is the responsibility of another step and needs its own test.

Testing **setHeaderIfAbsent**:

~~~java
@Test
void shouldKeepExistingHeaderWhenUsingSetHeaderIfAbsent() {
    Message<String> message = MessageBuilder
        .withPayload("ready")
        .setHeader("source", "gateway")
        .setHeaderIfAbsent("source", "fallback")
        .build();

    assertEquals("gateway", message.getHeaders().get("source"));
}
~~~

Testing copy and remove:

~~~java
@Test
void shouldCopyMessageAndRemoveInternalHeader() {
    Message<String> original = MessageBuilder
        .withPayload("hello")
        .setHeader("correlationId", "corr-1")
        .setHeader("internalDebug", true)
        .build();

    Message<String> copied = MessageBuilder
        .fromMessage(original)
        .setHeader("source", "worker")
        .removeHeader("internalDebug")
        .build();

    assertEquals("hello", copied.getPayload());
    assertEquals("corr-1", copied.getHeaders().get("correlationId"));
    assertEquals("worker", copied.getHeaders().get("source"));
    assertFalse(copied.getHeaders().containsKey("internalDebug"));

    assertTrue(original.getHeaders().containsKey("internalDebug"));
}
~~~

The final assertion confirms that creating the new message does not modify the original message.

Testing header immutability:

~~~java
@Test
void shouldRejectDirectHeaderMutation() {
    Message<String> message = MessageBuilder
        .withPayload("hello")
        .build();

    assertThrows(
        UnsupportedOperationException.class,
        () -> message.getHeaders().put("source", "worker")
    );
}
~~~

This tests the behavior of **MessageHeaders**. In application code, prefer the builder/accessor API rather than relying on catching exceptions from map modification attempts.

## 5. When Headers Need to Change: MessageHeaderAccessor

**MessageHeaderAccessor** provides a controlled API for manipulating headers. It is useful when you need to build a message with many headers, work with native headers, or need a transport-specific accessor.

Example of creating a message via an accessor:

~~~java
MessageHeaderAccessor accessor = new MessageHeaderAccessor();
accessor.setHeader("correlationId", "corr-200");
accessor.setHeader("source", "billing-service");

Message<String> message = MessageBuilder
    .withPayload("payment received")
    .setHeaders(accessor)
    .build();
~~~

For STOMP, **StompHeaderAccessor** provides specialized APIs for working with STOMP commands and native headers. For messages supporting user/session routing, **SimpMessageHeaderAccessor** provides headers intended for Spring Messaging over WebSocket.

Do not treat every application header as a transport native header. Native headers are metadata managed by the protocol or adapter. When reading or writing native headers, use the corresponding accessor to avoid confusing internal Spring headers with wire headers.

### Testing Headers via an Accessor

A test can verify headers created through an accessor:

~~~java
@Test
void shouldCreateMessageUsingHeaderAccessor() {
    MessageHeaderAccessor accessor = new MessageHeaderAccessor();
    accessor.setHeader("correlationId", "corr-200");
    accessor.setHeader("source", "billing-service");

    Message<String> message = MessageBuilder
        .withPayload("payment received")
        .setHeaders(accessor)
        .build();

    assertEquals(
        "corr-200",
        message.getHeaders().get("correlationId")
    );
    assertEquals(
        "billing-service",
        message.getHeaders().get("source")
    );
}
~~~

If using an accessor to modify an existing message, you need to understand its mutable state and when the accessor becomes frozen. Do not keep a mutable accessor beyond the scope of processing the message, and do not share it across threads.

## 6. What Does MessageConverter Do?

**MessageConverter** converts payloads between Java objects and the data representation required by a message transport or endpoint. The two main methods are:

- **toMessage(payload, headers)**: converts an object into a **Message<?>**.
- **fromMessage(message, targetClass)**: converts the message payload into an object of the target type.

A converter may inspect the content type to select the appropriate format. For example, a JSON converter serializes an object to JSON and deserializes JSON into a DTO.

Some common converters:

| Converter | Suitable Data |
|---|---|
| **StringMessageConverter** | Text strings |
| **ByteArrayMessageConverter** | Byte arrays |
| **SimpleMessageConverter** | Certain simple types, Serializable, and types supported by the implementation |
| **MappingJackson2MessageConverter** | Java objects and JSON via Jackson 2 |
| **CompositeMessageConverter** | Combines multiple converters in a list |

Class and module names may differ across Spring/Jackson generations. Check the dependency version in use before choosing a specific converter.

**MessageConverter** in Spring Messaging is not synonymous with **HttpMessageConverter** in Spring MVC. They play a similar role in data conversion, but belong to different abstractions and pipelines.

## 7. Testing a JSON Converter

Example using **MappingJackson2MessageConverter** to convert an event into a JSON message and then back into a DTO.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.util.MimeTypeUtils;

class MessageConverterTest {

    @Test
    void shouldConvertEventToJsonAndBack() {
        MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();

        OrderCreatedEvent event =
            new OrderCreatedEvent("O-100", "CREATED");

        MessageHeaders headers = new MessageHeaders(Map.of(
            MessageHeaders.CONTENT_TYPE,
            MimeTypeUtils.APPLICATION_JSON
        ));

        Message<?> jsonMessage = converter.toMessage(event, headers);

        assertNotNull(jsonMessage);
        assertInstanceOf(String.class, jsonMessage.getPayload());
        assertTrue(
            ((String) jsonMessage.getPayload()).contains("\"orderId\":\"O-100\"")
        );

        Object converted = converter.fromMessage(
            jsonMessage,
            OrderCreatedEvent.class
        );

        assertInstanceOf(OrderCreatedEvent.class, converted);
        assertEquals(event, converted);
    }
}
~~~

The test verifies three things:

1. The converter can create a message from the DTO.
2. The converted payload has the expected JSON format.
3. The JSON can be read back into the correct DTO type while preserving data.

In real-world projects, you should check the message's content type, ObjectMapper configuration, naming strategy, date/time module, and unknown-properties policy. Do not only check that the JSON contains a substring if the contract requires an exact structure; you can parse the JSON and compare individual fields or compare against a normalized JSON fixture.

### Testing Unsupported Payloads in a Converter

A converter may return **null** when it does not support the payload type or requested format. Therefore, tests should verify both successful conversions and cases that cannot be converted.

~~~java
@Test
void shouldReturnNullWhenTargetTypeIsUnsupported() {
    MappingJackson2MessageConverter converter =
        new MappingJackson2MessageConverter();

    Message<byte[]> message = MessageBuilder
        .withPayload(new byte[] {1, 2, 3})
        .setHeader(
            MessageHeaders.CONTENT_TYPE,
            MimeTypeUtils.APPLICATION_OCTET_STREAM
        )
        .build();

    Object result = converter.fromMessage(message, OrderCreatedEvent.class);

    assertNull(result);
}
~~~

Exact behavior also depends on the converter and version configuration. If the converter sits in a pipeline with multiple delegates, another converter may handle the message after the first one does not recognize it. Therefore, test both individual converters and the entire converter chain used by the application.

## 8. Testing Headers and Payload Independently

A common mistake is accidentally serializing metadata into the payload or assuming a header will automatically become a JSON field.

For example, a message with an event payload and a correlation ID:

~~~java
Message<OrderCreatedEvent> message = MessageBuilder
    .withPayload(new OrderCreatedEvent("O-100", "CREATED"))
    .setHeader("correlationId", "corr-100")
    .setHeader(
        MessageHeaders.CONTENT_TYPE,
        MimeTypeUtils.APPLICATION_JSON
    )
    .build();
~~~

When the converter serializes the payload, the object being converted is **OrderCreatedEvent**. The **correlationId** header remains in **MessageHeaders**; it does not automatically become a field in JSON. Transport adapters may map certain headers to native headers or metadata, depending on the protocol.

You should write separate assertions:

~~~java
assertEquals("O-100", message.getPayload().orderId());
assertEquals(
    "corr-100",
    message.getHeaders().get("correlationId")
);
assertEquals(
    MimeTypeUtils.APPLICATION_JSON,
    message.getHeaders().get(MessageHeaders.CONTENT_TYPE)
);
~~~

Separating assertions helps pinpoint whether an error lies in the payload, the headers, or the converter.

## 9. Testing Converter Chains and Endpoint Configuration

When an application supports multiple formats, a single converter may not be enough. **CompositeMessageConverter** lets you combine multiple converters to find a suitable one.

Example of creating a composite converter:

~~~java
CompositeMessageConverter converter = new CompositeMessageConverter(
    List.of(
        new StringMessageConverter(),
        new ByteArrayMessageConverter(),
        new MappingJackson2MessageConverter()
    )
);
~~~

Delegate ordering and MIME-type support affect which converter is selected. If two converters accept the same payload type or content type, you must check the actual order and configuration. Do not rely on arbitrary ordering or undocumented defaults.

In Spring STOMP, converters are configured for the message broker and are used when converting payloads of messages going to/from handlers. **SimpMessagingTemplate** also uses converters to support **convertAndSend** and **convertAndReceive**.

Example of sending an object:

~~~java
messagingTemplate.convertAndSend(
    "/topic/orders/created",
    event,
    Map.of("correlationId", "corr-100")
);
~~~

When testing a template or endpoint, verify the destination, payload, and headers after conversion. A unit test that only calls the converter does not prove that the broker adapter mapped headers as intended.

### Distinguishing RSocket Codecs

With RSocket in Spring, data payload conversion is typically configured through **RSocketStrategies** with **Encoder** and **Decoder**. This is the codec abstraction for RSocket; you should not assume you can replace it with **MessageConverter** from STOMP or messaging templates.

If an application supports multiple transports, test separately:

- Spring Message and MessageConverter in the corresponding messaging pipeline.
- Encoder/Decoder and MIME types in RSocket.
- Native headers/metadata mapping of each transport.

Sharing the same DTO does not mean every transport will serialize it the same way.

## 10. Testing Conversion Errors and Invalid Data

Beyond success cases, you need to test missing data, wrong types, invalid JSON, and unsupported content types.

Scenarios to verify:

- Malformed JSON payload.
- Valid JSON that is missing a required field.
- Field value with an incompatible type.
- Content type that does not match the actual payload.
- Target class not supported by the converter.
- Required header such as correlation ID is missing.
- Header value with the wrong type or wrong format.
- Payload that is too large or exceeds limits allowed by the application.

Do not swallow conversion errors and return an empty DTO or an unclear default value. Turn the error into a meaningful exception or error signal, log safely, and return an error according to the transport's contract.

For headers, validation should take place at the message ingestion boundary. For example:

~~~java
String correlationId = message.getHeaders().get(
    "correlationId",
    String.class
);

if (correlationId == null || correlationId.isBlank()) {
    throw new IllegalArgumentException(
        "Missing correlationId header"
    );
}
~~~

Do not include full headers or sensitive payloads in exception messages. Only log metadata that is permitted.

## 11. Testing Checklist

- [ ] MessageBuilder creates the correct payload and application headers.
- [ ] **setHeaderIfAbsent** preserves existing headers.
- [ ] **copyHeaders** and **copyHeadersIfAbsent** are used with the right semantics.
- [ ] **fromMessage** creates a new message without modifying the original message.
- [ ] **removeHeader** removes the intended metadata.
- [ ] MessageHeaders are not mutated directly.
- [ ] System headers and application headers are clearly distinguished.
- [ ] Content type is set accurately for the payload format.
- [ ] Converter serializes and deserializes the right data types.
- [ ] Unsupported payloads are handled properly by the converter.
- [ ] Converter chain selects the right delegate according to configuration.
- [ ] Headers and payload are tested independently.
- [ ] Native headers are tested against the proper transport adapter.
- [ ] RSocket Encoder/Decoder are tested separately with their corresponding MIME types.
- [ ] Tests exist for malformed JSON, missing fields, wrong types, and missing required headers.

## 12. References

- [Spring Framework Reference: Message](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message.html) — message model, headers, and accessors.
- [Spring Framework API: MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html) — creating messages, copying, and updating headers.
- [Spring Framework API: MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html) — standard headers and immutability.
- [Spring Framework API: MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html) — payload conversion contract.
- [Spring Framework Reference: STOMP Message Conversion](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html) — configuring converters for STOMP messaging.
- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — RSocketStrategies and Encoder/Decoder codecs.
