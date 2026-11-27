# Type Conversion When Proactively Polling Messages

With a standard consumer, Spring Cloud Stream invokes the handler function when a message arrives and can infer the payload type from the Function or Consumer signature. With a pollable consumer, the application proactively calls PollableMessageSource.poll() to retrieve a message. Since the callback receives a Message<?>, the target type cannot always be inferred from a lambda. Therefore, Spring Cloud Stream provides an overload accepting ParameterizedTypeReference<?> to supply a type hint for payload conversion.

This lesson focuses on reading messages into POJOs, collections, and generic types; coordinating the target type with content-type; and handling conversion errors inside the polling loop. This is part of Spring Cloud Stream's Supplier/Function/Consumer and binding model: the pollable source provides the input, the binder connects to Kafka, RabbitMQ, or another polling-capable broker, and the converter transforms the wire payload into the type required by business logic.

## 1. PollableMessageSource and Payload Types

PollableMessageSource represents a message source from which the application pulls data on demand. Instead of the framework automatically invoking a consumer whenever a message arrives, the application calls poll() from a loop, scheduler, or custom orchestrator.

A pollable source can be declared using the spring.cloud.stream.pollable-source property. For example:

~~~yaml
spring:
  cloud:
    stream:
      pollable-source: orders
      bindings:
        orders-in-0:
          destination: orders.created
          group: order-reader
          content-type: application/json
~~~

The name orders creates the input binding orders-in-0. The binding connects to the orders.created destination under the order-reader consumer group. content-type describes the payload format so the message converter can choose how to decode it.

Pollable consumer support and acknowledgment details depend on the binder. Before adopting this model in production, verify that your binder and version support pollable sources, along with how it handles timeouts, acknowledgments, and redelivery.

When the application calls poll(), the callback receives a Message<?>. Without passing target type information, the payload may remain a byte array, a string, or whatever type the binder/converter already produced along the data path. When a specific type is needed, provide a ParameterizedTypeReference:

~~~java
boolean received = ordersIn.poll(
        message -> {
            OrderCreated order = (OrderCreated) message.getPayload();
            process(order);
        },
        new ParameterizedTypeReference<OrderCreated>() {});
~~~

This overload has the signature:

~~~java
boolean poll(MessageHandler handler, ParameterizedTypeReference<?> type);
~~~

type is a conversion hint. The framework uses it alongside the message or binding content-type to locate a suitable converter and convert the payload to the requested type. After successful conversion, the callback can retrieve the payload as OrderCreated.

## 2. Declaring Data Types and Polling a POJO

Suppose the producer emits an order event as JSON:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "ORD-1001",
  "customerId": "CUS-01",
  "totalMinorUnits": 125500
}
~~~

Declare the corresponding Java type:

~~~java
record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        long totalMinorUnits) {}
~~~

Inject PollableMessageSource and pass the target type to poll():

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.stream.binder.PollableMessageSource;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderPollingConfiguration {

    @Bean
    ApplicationRunner orderPoller(PollableMessageSource ordersIn) {
        return args -> {
            boolean received = ordersIn.poll(
                    message -> {
                        OrderCreated order =
                                (OrderCreated) message.getPayload();
                        System.out.printf(
                                "Order %s from %s, total=%d%n",
                                order.orderId(),
                                order.customerId(),
                                order.totalMinorUnits());
                    },
                    new ParameterizedTypeReference<OrderCreated>() {});

            if (!received) {
                System.out.println("No order message is available");
            }
        };
    }
}
~~~

The example calls poll() once when ApplicationRunner runs to demonstrate conversion. In a continuously running application, poll must be called periodically or inside a controlled loop; do not use a single invocation like this as a continuously running consumer.

poll() returns true when a message was received and processed successfully, or false when no message was available to process on that call. You can use this result to decide whether to wait, continue reading a batch, or update metrics.

## 3. Converting Collections and Generic Types

When the payload is a collection, the target type must preserve element type information. If you only use List.class, Java type erasure drops the element type; the converter might only produce a list of Maps instead of OrderLine.

Example where the JSON payload is a list of order lines:

~~~json
[
  { "productId": "SKU-01", "quantity": 2 },
  { "productId": "SKU-02", "quantity": 1 }
]
~~~

Declare the type:

~~~java
record OrderLine(String productId, int quantity) {}
~~~

Use ParameterizedTypeReference<List<OrderLine>>:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.core.ParameterizedTypeReference;

ParameterizedTypeReference<List<OrderLine>> orderLinesType =
        new ParameterizedTypeReference<List<OrderLine>>() {};

boolean received = ordersIn.poll(
        message -> {
            @SuppressWarnings("unchecked")
            List<OrderLine> lines =
                    (List<OrderLine>) message.getPayload();

            for (OrderLine line : lines) {
                reserve(line.productId(), line.quantity());
            }
        },
        orderLinesType);
~~~

Generic target types also apply to nested maps:

~~~java
ParameterizedTypeReference<Map<String, List<OrderLine>>> groupedLinesType =
        new ParameterizedTypeReference<
                Map<String, List<OrderLine>>>() {};
~~~

ParameterizedTypeReference preserves type information at runtime via an anonymous subclass. Because of this, the converter knows the Map contains List<OrderLine> instead of seeing only a raw Map type.

Make sure the actual JSON structure matches the target type. If the payload is an object with an items field containing a list, the target type must be a wrapper record with an items field; you cannot ask the converter to automatically turn the entire object into List<OrderLine>.

## 4. Distinguishing content-type from Target Type

content-type and ParameterizedTypeReference answer two different questions:

- content-type specifies the format in which the input data is represented, such as JSON, plain text, or a byte array.
- ParameterizedTypeReference specifies the Java type the application wants to receive the payload as, such as OrderCreated or List<OrderLine>.

Both pieces of information are used together to select a MessageConverter. Setting content-type: application/json alone is not enough to determine whether the JSON should become OrderCreated, List<OrderLine>, or another type. Conversely, requesting OrderCreated does not tell the converter whether the input bytes are JSON, Avro, or a custom format without metadata or a matching converter.

JSON configuration example:

~~~yaml
spring:
  cloud:
    stream:
      pollable-source: orders
      bindings:
        orders-in-0:
          destination: orders.created
          group: order-reader
          content-type: application/json
~~~

Common combinations:

| Content type | Typical Data | Suitable Target Type |
|---|---|---|
| application/json | JSON object or array | POJO, record, Map, List<T> |
| text/plain | Text | String |
| application/octet-stream | Raw bytes | byte[] |

Spring Cloud Stream includes default converters for JSON, byte arrays, and text. If no converter supports the content type/target type pair, conversion will fail. Check the contentType header, binding configuration, and target type before writing a custom converter.

## 5. Reading Headers Alongside the Converted Payload

The conversion hint applies to the payload; the callback still receives a Spring Message<?>, so you can read headers for metadata:

~~~java
ordersIn.poll(
        message -> {
            OrderCreated order =
                    (OrderCreated) message.getPayload();

            String eventId =
                    (String) message.getHeaders().get("eventId");
            String correlationId =
                    (String) message.getHeaders().get("correlationId");

            audit(order, eventId, correlationId);
        },
        new ParameterizedTypeReference<OrderCreated>() {});
~~~

Headers can carry an event ID, correlation ID, or tracing information. Do not assume every producer header is preserved intact by the broker; binders may map or filter headers depending on broker capabilities. If a header is mandatory for business logic, test it through the actual binder.

Do not use headers as a substitute for payload target type. For example, eventType: OrderCreated does not automatically cause the converter to instantiate OrderCreated if the callback does not provide a target type or the framework lacks corresponding type metadata.

## 6. Reading Multiple Payload Types from the Same Source

A destination may carry multiple event types. If each message has a different structure, avoid forcing everything into a single POJO and checking casts. You can use a shared envelope, or read the payload as a Map/JsonNode and route by event type.

Example using an envelope:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

record EventEnvelope(
        String eventType,
        int schemaVersion,
        JsonNode data) {}
~~~

Reading the envelope from the pollable source:

~~~java
ordersIn.poll(
        message -> {
            EventEnvelope envelope =
                    (EventEnvelope) message.getPayload();

            switch (envelope.eventType()) {
                case "OrderCreated" ->
                        handleCreated(envelope.data());
                case "OrderCancelled" ->
                        handleCancelled(envelope.data());
                default ->
                        handleUnknown(envelope.eventType());
            }
        },
        new ParameterizedTypeReference<EventEnvelope>() {});
~~~

The envelope should be a contract agreed upon by producer and consumer. When data has a different structure per event type, it can be further converted to a concrete type using ObjectMapper or a dedicated converter after validating the event type and schema version. Validate input before converting; never trust an arbitrary event type value from an external source.

Another option is using multiple bindings, each with its own content type and payload type. This approach is often easier to govern if event types have different lifecycles, access permissions, or consumer groups.

## 7. When Do You Need a Custom MessageConverter?

Default converters handle common formats. Only create a custom converter when payloads use a proprietary format or have conversion rules not supported out of the box. The converter must declare the content type it handles and the target types it supports.

Illustrative example of a converter for an internal binary format application/order-binary:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.converter.AbstractMessageConverter;
import org.springframework.util.MimeType;

class OrderBinaryMessageConverter extends AbstractMessageConverter {

    OrderBinaryMessageConverter() {
        super(new MimeType("application", "order-binary"));
    }

    @Override
    protected boolean supports(Class<?> targetClass) {
        return OrderCreated.class.equals(targetClass);
    }

    @Override
    protected Object convertFromInternal(
            Message<?> message,
            Class<?> targetClass,
            Object conversionHint) {

        byte[] bytes = (byte[]) message.getPayload();
        return OrderBinaryCodec.decode(bytes);
    }
}
~~~

Register the converter as a bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderConverterConfiguration {

    @Bean
    MessageConverter orderBinaryMessageConverter() {
        return new OrderBinaryMessageConverter();
    }
}
~~~

OrderBinaryCodec represents the decoder for the custom format. A production converter must validate length, magic/version bytes, malformed data, and size limits before decoding. Do not use this example to replace a binder's Avro/Protobuf serializer if the system already uses dedicated serializers/deserializers.

Custom converters are added to Spring Cloud Stream's converter stack and may take precedence over default converters. Therefore, the scope of supports() and the content type must be narrow enough not to accidentally intercept ordinary JSON or text messages.

## 8. Scheduled Polling and Processing a Batch

Avoid creating a continuous busy polling loop when no messages exist. You can use @Scheduled to control the polling pace and cap the number of messages per pass:

~~~java
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.cloud.stream.binder.PollableMessageSource;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableScheduling
class PollingScheduleConfiguration {}

@Component
class OrderBatchPoller {

    private final PollableMessageSource ordersIn;

    OrderBatchPoller(PollableMessageSource ordersIn) {
        this.ordersIn = ordersIn;
    }

    @Scheduled(fixedDelay = 500)
    void pollBatch() {
        for (int i = 0; i < 50; i++) {
            boolean received = ordersIn.poll(
                    message -> {
                        OrderCreated order =
                                (OrderCreated) message.getPayload();
                        process(order);
                    },
                    new ParameterizedTypeReference<OrderCreated>() {});

            if (!received) {
                break;
            }
        }
    }
}
~~~

The example caps each pass at 50 messages so a single batch does not monopolize the scheduler indefinitely when the destination always has data. Tune batch size and delay according to throughput, processing time, and broker capacity. If the callback takes a long time to execute, consider thread pools, concurrency, and how the binder manages acknowledgment.

If the application has multiple pollable sources, distinguish each binding by name and qualifier according to how your Spring Cloud Stream version creates beans. Do not inject a single source and assume it represents all input bindings.

## 9. Conversion Errors and Error Handling During Polling

Conversion can fail before the callback runs business logic, for example:

- Malformed JSON or JSON that cannot be mapped to the target type.
- Missing required fields or incompatible field types.
- Declared content-type does not match the actual format.
- The callback casts the payload to a different type than requested.
- Truncated binary payload or unsupported schema/version.

You can catch errors around the poll call for logging and observability:

~~~java
try {
    boolean received = ordersIn.poll(
            message -> {
                OrderCreated order =
                        (OrderCreated) message.getPayload();
                process(order);
            },
            new ParameterizedTypeReference<OrderCreated>() {});

    if (!received) {
        metrics.increment("orders.poll.empty");
    }
}
catch (Exception ex) {
    log.error("Could not poll or convert an order message", ex);
    metrics.increment("orders.poll.failure");
}
~~~

Spring Cloud Stream configures an error channel for a pollable source. If the callback throws an exception, an ErrorMessage may be sent to the binding's error channel, typically named <destination>.<group>.errors, and bridged to Spring Integration's global errorChannel. If no subscriber handles the error channel, the error may only be logged and the message acknowledged as successfully processed. Therefore, never assume that merely throwing an exception guarantees the message will be redelivered.

If the error handler throws an exception, the message is typically rejected by default and not requeued. With binders that support it, you can throw RequeueCurrentMessageException directly from the callback to ask the broker to return the message to the queue; this bypasses the error channel. Exact behavior depends on the binder and configuration; unbounded requeuing can create an error loop and stall the consumer.

Classify errors before choosing an action:

| Error Type | Example | Handling Approach |
|---|---|---|
| Permanent data error | Malformed JSON, invalid required field | Log, isolate, or send to DLQ; do not retry indefinitely |
| Transient error | Dependent service timeout | Bounded retry/backoff or requeue per policy |
| Programming error | Invalid cast, NullPointerException | Alert, fix code; do not create an infinite requeue loop |
| Infrastructure error | Broker/registry unavailable | Monitor and recover according to binder and operational policy |

## 10. Acknowledgment and Callback Completion Timing

Normally, poll() acknowledges the message when MessageHandler finishes normally. If the callback finishes abnormally, the message is rejected by the pollable source's default mechanism; rejection does not automatically mean requeue. Changing this behavior requires an error handler, exception, or appropriate binder configuration.

Therefore, the callback should finish only after the work the application considers complete has been performed. Do not spawn an async task and return immediately if message acknowledgment must wait for that task to complete:

~~~java
// Unsuitable if acknowledgment must wait for processing:
ordersIn.poll(message -> {
    executor.submit(() -> process(message));
});
~~~

In the example above, the callback may finish before process() completes; the pollable source may acknowledge the message too early. If asynchronous processing is needed, await completion within the callback scope, use an appropriate reactive/binder model, or persist the work durably before the callback returns.

Acknowledgment, transactions, and redelivery differ across Kafka, RabbitMQ, and Pulsar. Check your binder's semantics, especially when the callback accesses a database or external service. Polling does not automatically create an atomic transaction between the broker and the database.

## 11. Distinguishing JSON Conversion from Native Serialization

For JSON, Spring Cloud Stream typically uses a MessageConverter based on content type and target type. For Avro or Protobuf, the application may use the binder's native serializer/deserializer or a dedicated converter.

If the binder has already decoded the payload into an object before the callback receives the message, no further conversion is needed. If the payload is still a byte[], you must know whether those bytes are JSON, Avro, Protobuf, or a custom format before decoding. ParameterizedTypeReference is only a type hint; it does not provide a schema registry, serializer, or binary decoding algorithm on its own.

When using the Kafka binder with native decoding, verify the corresponding deserializer and schema registry settings. With RabbitMQ or Pulsar, check how the binder propagates content type, schema metadata, and payload types. Do not copy Kafka native serializer configuration to another binder.

## 12. Testing Type Conversion

Tests should cover both simple and generic payloads:

1. Send valid JSON and verify the payload becomes the expected POJO.
2. Send a JSON array and verify elements have the concrete type, not untyped Maps.
3. Send a payload missing fields or with wrong types and verify the error is observed.
4. Change content type to verify the right converter is selected.
5. Send a message with correlation/event ID headers and verify required metadata remains intact.
6. Test callback success, callback throwing an exception, and binder ack/requeue behavior.
7. Test against a real broker because standalone converter tests do not prove native decoding and broker acknowledgment.

Example standalone JSON converter test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.http.MediaType;

class OrderPayloadConversionTest {

    @Test
    void convertsJsonPayloadToOrderCreated() {
        String json = """
                {
                  "eventId": "evt-1",
                  "orderId": "ORD-1",
                  "customerId": "CUS-1",
                  "totalMinorUnits": 125500
                }
                """;

        Message<String> message = MessageBuilder.withPayload(json)
                .setHeader(MessageHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON)
                .build();

        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();

        OrderCreated order =
                (OrderCreated) converter.fromMessage(message, OrderCreated.class);

        assertEquals("ORD-1", order.orderId());
        assertEquals(125500L, order.totalMinorUnits());
    }
}
~~~

This is a standalone converter test illustrating the relationship between content type and target class. In a Spring Cloud Stream application, converters are managed within the framework's converter stack; to verify that the poll(handler, type) overload works properly with the binder, add integration tests using the pollable source and the corresponding broker/test environment.

## 13. Pre-Deployment Checklist

- Pollable source is declared and the *-in-0 binding points to the correct destination/group.
- content-type reflects the actual payload format.
- poll(handler, ParameterizedTypeReference<?>) provides the right target type, including generic types when needed.
- Callback validates payload and headers before executing side effects.
- Default converters suffice; custom converters are added only for proprietary formats.
- Conversion failures have clear error channels, logs, metrics, and reject/requeue policies.
- Callback does not return before required work finishes if acknowledgment depends on the callback.
- Retries/requeues are bounded and permanently invalid messages are isolated.
- Conversion, acknowledgment, and real binder behavior have all been tested.

With a pollable consumer, the application actively pulls messages and must therefore supply enough information for the converter to know both the input format and the target type. content-type describes the payload on the wire; ParameterizedTypeReference describes the Java type the callback expects. When these two pieces align and a converter supports them, Spring Cloud Stream can convert JSON, text, or matching data into POJOs or generic collections. Combining proper conversion with intentional error handling and acknowledgment helps pollable consumers read data safely and predictably in asynchronous environments.
