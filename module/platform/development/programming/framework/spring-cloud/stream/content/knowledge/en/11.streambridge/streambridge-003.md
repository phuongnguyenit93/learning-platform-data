# Sending POJOs or Messages and Specifying contentType

`StreamBridge` allows a Java component to send data to a Spring Cloud Stream output binding without turning that component into a `Supplier` or `Function`. The data sent can be a POJO (Plain Old Java Object) or a Spring `Message<?>`. When sending, the application needs to specify the content format so the binder and consumer interpret the payload properly. For JSON, you can declare `content-type` on the binding, pass a `MimeType` directly to `StreamBridge.send`, or set the content type in the `Message` headers.

These three approaches serve different scenarios. Binding configuration fits when an output always uses the same format; the overload accepting `MimeType` fits when the send call needs to specify the format on the spot; `Message` headers fit when format and metadata need to travel together with the payload. Choose one clear configuration source for each message and avoid conflicting content type values.

## 1. StreamBridge sends data from imperative code

In the functional model, Spring Cloud Stream connects `Supplier`, `Function`, or `Consumer` to bindings. However, some event-publishing flows start from a REST controller, business service, scheduled task, or callback. `StreamBridge` provides an API to send data from those imperative components to an output binding.

Example event DTOs:

```java
public record OrderCreated(
    String eventId,
    String orderId,
    long total
) {}

public record OrderStatusChanged(
    String eventId,
    String orderId,
    String status
) {}
```

Declaring and injecting `StreamBridge`:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }
}
```

The `send` method accepts the output binding name and the data to send. The boolean result indicates whether the send operation through the binding/channel inside the application was accepted; a `true` value alone should not be treated as confirmation that the broker durably stored the message.

## 2. Sending a POJO directly

If the binding is already configured with `content-type: application/json`, you can send a POJO directly:

```java
public boolean publish(OrderCreated event) {
    return streamBridge.send("orders-out-0", event);
}
```

Binding configuration:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
```

In the example, `orders-out-0` is the binding name in the application; `orders.created` is the destination that the binder maps to the corresponding topic, exchange, or broker topic. `event` is the POJO payload. The message converter uses the binding's content type to convert the payload into the configured format before sending.

When sending a POJO, Spring Cloud Stream creates a message for the binding. The application does not need to build a `Message<?>` manually if no extra headers or metadata are needed. This approach fits when only sending a payload and every message on the binding uses the same format.

## 3. Specifying contentType via StreamBridge overload

When you need to choose the format right at the send call, use the overload accepting `MimeType`:

```java
import org.springframework.util.MimeTypeUtils;

public boolean publishJson(OrderCreated event) {
    return streamBridge.send(
        "orders-out-0",
        MimeTypeUtils.APPLICATION_JSON,
        event
    );
}
```

The second parameter is `MimeType`, and the third parameter is the data to send. `MimeTypeUtils.APPLICATION_JSON` represents `application/json`. Other constants in `MimeTypeUtils` can be used for appropriate text or binary formats, such as `TEXT_PLAIN` and `APPLICATION_OCTET_STREAM`.

If using a text format, the payload also needs an appropriate type:

```java
public boolean publishStatus(String status) {
    return streamBridge.send(
        "status-out-0",
        MimeTypeUtils.TEXT_PLAIN,
        status
    );
}
```

The specified format must match the payload type and an available converter. Attaching `application/json` to a plain string that does not contain valid JSON does not turn that string into a JSON object. Similarly, `application/octet-stream` generally fits a `byte[]` payload or binary data that consumers know how to read.

The `MimeType` overload is useful when the same component sends multiple data types or when the format must be decided at runtime. If a binding always uses JSON, declaring `content-type` at the binding level is usually easier to manage and avoids repeating it on every call.

## 4. Sending a Message to carry headers

When an event ID, correlation ID, or custom metadata is needed, create a Spring `Message<T>` using `MessageBuilder`:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageBuilder;
import org.springframework.messaging.MessageHeaders;
import org.springframework.util.MimeTypeUtils;

public boolean publishWithHeaders(OrderCreated event) {
    Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .setHeader("eventId", event.eventId())
        .setHeader("correlationId", "corr-42")
        .build();

    return streamBridge.send("orders-out-0", message);
}
```

`Message<T>` consists of two parts:

- `payload`: the business data, here `OrderCreated`.
- `headers`: accompanying metadata, here content type, event ID, and correlation ID.

`MessageHeaders.CONTENT_TYPE` is the standard Spring Messaging header name for content type. The value should be a `MimeType`, such as `MimeTypeUtils.APPLICATION_JSON`. Custom headers should use stable names and data types that the binder can map.

When sending `Message<?>`, add only the headers that are needed. Do not copy all headers from an HTTP request or an external message without filtering, as they may contain tokens, cookies, personal data, or internal metadata unsuitable for broadcasting across the broker.

## 5. Choosing how to set contentType

The three common approaches can be compared as follows:

| Approach | Example | When to use |
|---|---|---|
| Binding configuration | `content-type: application/json` | Every message on the binding uses the same format |
| `StreamBridge.send` overload | `send(binding, MimeTypeUtils.APPLICATION_JSON, event)` | Format is decided at the send point |
| Header in `Message` | `setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)` | Message needs to carry content type along with other headers |

Do not configure three different sources with inconsistent values. For example, declaring JSON on the binding while the message header specifies `text/plain` makes the intended contract hard to understand and may cause the converter to behave unexpectedly. Set content type consistently and test the actual behavior of the Spring Cloud Stream/binder version in use.

A maintainable rule of thumb is:

- Use binding content type for dedicated outputs with a fixed format.
- Use the `MimeType` overload when one send point handles multiple payload types/formats.
- Use a `Message` header when the message must carry explicit metadata and the caller is responsible for constructing the message.

## 6. Static bindings and dynamic destinations

The name passed to `StreamBridge.send` is the output binding name. If the binding is already declared, Spring Cloud Stream uses that binding and its properties such as destination, binder, content type, partitioning, and producer settings.

Static binding example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        audit-out-0:
          destination: audit.events
          content-type: application/json
```

```java
streamBridge.send("audit-out-0", auditEvent);
```

If the binding name does not yet exist, `StreamBridge` can create a dynamic output binding. In that case, the target name is used to create a dynamic binding according to the framework's mechanism. Example:

```java
streamBridge.send("tenant-events", MimeTypeUtils.APPLICATION_JSON, event);
```

Dynamic destinations are useful when the target destination is determined at runtime, but arbitrary input data should never dictate topic/queue names. Control the list of allowed destinations and configure the binder accordingly. For destinations known in advance, static bindings make configuration, permissions, observability, and deployment more predictable.

Dynamic bindings can be pre-created before sending via `spring.cloud.stream.output-bindings` configuration if the application needs to initialize specific output bindings at startup. Syntax and interaction with other bindings should be verified against the framework version in use.

## 7. Message conversion and native encoding

Specifying `contentType` mainly provides information for Spring Cloud Stream's message conversion. It does not automatically configure a Kafka serializer, RabbitMQ native converter, or Pulsar schema if the binding is using native encoding.

Distinguish two cases:

**Using message conversion:** the POJO is converted according to the content type, e.g., JSON. Producer and consumer must agree on the content type and corresponding converter/schema.

**Using native encoding:** the binder/client uses the broker's own serializer. In that case, the corresponding serializer/deserializer must be configured in the binder extension properties. Simply setting `contentType` does not replace native serializer configuration.

Example of an output binding using native encoding with Kafka:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          producer:
            use-native-encoding: true
      kafka:
        bindings:
          orders-out-0:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
                value.serializer: org.apache.kafka.common.serialization.StringSerializer
```

This example assumes the producer sends string values compatible with `StringSerializer`; if sending a POJO, you need a serializer that supports the POJO type or convert the payload into the corresponding form before sending. Do not use `StringSerializer` for an arbitrary object.

With RabbitMQ and Pulsar, native conversion/schema has its own configuration. Check the binder documentation and client version. `MimeType` does not make an incompatible native serializer compatible.

## 8. Complete example: publishing order events

A publisher can support both sending POJOs and `Message`:

```java
import java.util.UUID;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageBuilder;
import org.springframework.messaging.MessageHeaders;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;

@Service
public class OrderEventPublisher {
    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }

    public boolean publishWithMetadata(OrderCreated event, String correlationId) {
        Message<OrderCreated> message = MessageBuilder
            .withPayload(event)
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
            .setHeader("eventId", event.eventId())
            .setHeader("correlationId", correlationId)
            .setHeader("publisher", "order-service")
            .build();

        return streamBridge.send("orders-out-0", message);
    }

    public boolean publishStatus(String orderId, String status) {
        OrderStatusChanged event = new OrderStatusChanged(
            UUID.randomUUID().toString(), orderId, status);

        return streamBridge.send(
            "order-status-out-0",
            MimeTypeUtils.APPLICATION_JSON,
            event
        );
    }
}
```

Corresponding configuration:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
        order-status-out-0:
          destination: orders.status
          content-type: application/json
```

Both bindings use JSON. The `publish` method sends a POJO and relies on the binding's content type. `publishWithMetadata` sends `Message<OrderCreated>` to carry headers. `publishStatus` specifies content type via the `StreamBridge.send` overload. In a real application, you can choose one consistent style instead of keeping multiple sending styles if there is no clear need.

## 9. Checking send results and handling errors

`StreamBridge.send` returns a boolean. Check the result and log with context when the binding does not accept the message:

```java
boolean accepted = streamBridge.send("orders-out-0", event);
if (!accepted) {
    throw new IllegalStateException("Output binding did not accept the order event");
}
```

A `true` result indicates the message was accepted through the application's send path. With asynchronous sending, broker publish failures may be reported through the binder's error mechanism after the call returns. Configure appropriate observability and error handling; do not reply to an inbound API call claiming the business data was durably stored by the broker based solely on the boolean.

If sending a message after updating a database, consider transactional outbox to avoid the case where the database commits but publishing fails. If producer retries can produce duplicates, attach a stable event ID and design idempotent consumers.

## 10. Testing POJOs, Messages, and contentType

Testing should verify both payload and metadata:

- Send a POJO through a binding with `content-type: application/json` and verify the consumer receives the expected DTO.
- Send a POJO using the `send(binding, MimeType, data)` overload and verify the format is processed properly.
- Send a `Message<T>` with `MessageHeaders.CONTENT_TYPE` and business headers; verify required headers are preserved across the binder.
- Try a content type incompatible with the payload to ensure conversion errors are detected.
- Test a message whose content type header conflicts with binding configuration and verify the actual rule of the version in use.
- Test dynamic destinations against an allow-list of permitted destinations; verify sending to destinations outside policy is rejected.
- Test with real Kafka, RabbitMQ, or Pulsar when verifying native encoding, header mapping, durability, and broker errors.

The Test Binder is useful for testing function and binding logic within the application scope. It does not prove that every serializer, converter, or header mapper of a real broker behaves identically. For critical flows, add integration tests using the actual production binder and broker.

## 11. Pre-send checklist

- [ ] Correct output binding name and destination selected.
- [ ] POJO payload has a clear, serializable type.
- [ ] Content type on binding, overload, or message header is chosen consistently.
- [ ] If sending `Message<?>`, only necessary and vetted headers are included.
- [ ] Determined whether the binding uses message conversion or native encoding.
- [ ] If using native encoding, the binder's serializer matches the payload type.
- [ ] Consumer has a compatible converter/deserializer and schema.
- [ ] Checked boolean return value and configured asynchronous publish error observability.
- [ ] Tested payload, content type, and headers with the real binder.

`StreamBridge` makes it easy to send POJOs or `Message<?>` from any imperative component of the application. When choosing the right content type on the binding, `MimeType` overload, or message header, producers and consumers can agree on how to interpret payloads. Keep the wire contract clear, pass only necessary metadata, and test through the real binder so messages arrive at consumers in the expected format.
