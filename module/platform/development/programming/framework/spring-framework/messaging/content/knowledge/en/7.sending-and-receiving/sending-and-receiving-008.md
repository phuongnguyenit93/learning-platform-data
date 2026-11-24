# convertAndSend, receiveAndConvert, and convertSendAndReceive

## Objectives

In Spring Messaging, applications typically work with business objects such as `OrderCreated`, `PaymentRequest`, or `StockReply`, whereas the messaging infrastructure exchanges `Message<?>` instances with payloads and headers. The `convertAndSend`, `receiveAndConvert`, and `convertSendAndReceive` methods bridge those two worlds using a `MessageConverter`.

After this lesson, you will be able to:

- Choose the right method for send-only, receive-only, or request-reply needs.
- Understand at which step data is converted and the role of `MessageConverter`.
- Choose the appropriate destination, default destination, and channel type.
- Configure send timeout and receive timeout, and handle cases with no message or no reply.
- Distinguish successful delivery to a channel from completed consumer processing.

## 1. Where These Methods Sit in Spring Messaging

These methods belong to the template API group in the `org.springframework.messaging.core` package:

- `MessageSendingOperations<D>` defines sending operations, including `send` and `convertAndSend`.
- `MessageReceivingOperations<D>` defines receiving operations, including `receive` and `receiveAndConvert`.
- `MessageRequestReplyOperations<D>` defines request-reply operations, including `sendAndReceive` and `convertSendAndReceive`.

Abstract classes share the common handling:

- `AbstractMessageSendingTemplate<D>` implements sending variants and payload conversion.
- `AbstractMessageReceivingTemplate<D>` adds message receiving and payload conversion.
- `AbstractMessagingTemplate<D>` adds request-reply.
- `GenericMessagingTemplate` is the concrete implementation using `MessageChannel` as the destination and capable of resolving destination names into channels.

In plain Spring Messaging applications, the commonly used class is:

~~~java
import org.springframework.messaging.core.GenericMessagingTemplate;

GenericMessagingTemplate template = new GenericMessagingTemplate();
~~~

This is the Spring Framework `spring-messaging` API. Integration frameworks such as Spring Integration, Spring AMQP, or Spring JMS also have templates and methods with similar names, but their destinations, converters, timeouts, and semantics may differ. Always verify the exact template type your application is using.

## 2. The Overall Picture

The three methods serve different purposes:

| Method | Input | Outcome | Purpose |
|---|---|---|---|
| `convertAndSend` | Java payload | Does not return payload | Converts payload into a Message and sends it |
| `receiveAndConvert` | Destination and target class | Java payload or `null` | Receives a Message and converts its payload to the desired type |
| `convertSendAndReceive` | Java request and reply target class | Java reply or `null` | Sends a request, waits for a reply, and converts the reply payload |

You can remember the data flow as follows:

~~~text
convertAndSend
Java payload -> MessageConverter -> Message -> MessageChannel

receiveAndConvert
MessageChannel -> Message -> MessageConverter -> Java payload

convertSendAndReceive
Java request -> MessageConverter -> request Message
             -> MessageChannel -> request handler
             -> reply Message -> MessageConverter -> Java reply
~~~

If the application already has a `Message<?>` and wants to keep control over headers, it can use `send`, `receive`, or `sendAndReceive` to work directly with messages instead of using the conversion methods.

## 3. What Does MessageConverter Do?

`MessageConverter` is the conversion contract between a Java payload and a `Message<?>`:

- `toMessage(payload, headers)`: creates a Message from a payload and headers.
- `fromMessage(message, targetClass)`: extracts the payload from a Message and converts it to the target type.

The template invokes the converter in whichever direction is needed. `convertAndSend` uses the Java object-to-Message direction; `receiveAndConvert` uses the Message-to-Java object direction; `convertSendAndReceive` uses both directions.

### 3.1. Beware of the Default Converter

Templates extending `AbstractMessageSendingTemplate` use `SimpleMessageConverter` by default.

`SimpleMessageConverter` only wraps a payload into a Message and extracts the payload if it is already compatible with the target type. It does not automatically turn POJOs into JSON, does not decode JSON into POJOs, and ignores content type information in headers.

For example, if you send an `OrderCreated` object through an in-process channel, the simple converter may keep that object as-is as the payload. This does not mean the object has been serialized for network transmission or stored as JSON.

If actual format conversion is required:

- Configure a `MessageConverter` suited to the exchange format, such as JSON or byte array.
- Ensure sender and receiver agree on format and data types.
- Set `MessageHeaders.CONTENT_TYPE` appropriately when the converter uses MIME types to choose how to convert.
- Verify how the adapter or broker forwards payloads and headers.

If the converter does not support the payload or cannot convert to the target type, the operation may throw `MessageConversionException`. Do not confuse conversion errors with the case of no message arriving before timeout.

## 4. convertAndSend: Converting a Payload to a Message and Sending

### 4.1. How It Works

`convertAndSend` accepts a Java object, converts it into a Message using the configured converter, and sends the Message to the destination.

Common usage forms:

~~~java
template.convertAndSend(destination, payload);

template.convertAndSend(destination, payload, headers);

template.convertAndSend(destination, payload, postProcessor);

template.convertAndSend(destination, payload, headers, postProcessor);
~~~

If the template has a default destination configured, the destination parameter can be omitted:

~~~java
template.setDefaultDestination(defaultChannel);
template.convertAndSend(payload);
~~~

If neither a destination is passed nor a default destination is configured, the template cannot determine where to send and will raise an error.

### 4.2. Headers and MessagePostProcessor

Headers add metadata to the Message, for example:

- `eventType`: event type.
- `correlationId`: identifier linking messages within the same processing flow.
- `traceId`: tracing identifier.
- `tenantId`: tenant scope.
- `contentType`: payload format.

`MessagePostProcessor` is invoked after Message creation, allowing the message to be modified before sending. Example:

~~~java
import java.util.Map;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.core.GenericMessagingTemplate;
import org.springframework.messaging.support.MessageBuilder;

void publish(
        GenericMessagingTemplate template,
        MessageChannel events,
        OrderCreated event) {

    template.convertAndSend(
        events,
        event,
        Map.of("eventType", "OrderCreated"),
        message -> MessageBuilder.fromMessage(message)
            .setHeader("traceId", "trace-1001")
            .build()
    );
}
~~~

This is an illustrative service method; `events` is an application-configured MessageChannel and `OrderCreated` is a domain payload type. The snippet is not a standalone program to run directly with `javac`.

### 4.3. Outcome and Limits

The method returns `void`. When using `GenericMessagingTemplate`, if the channel rejects the send or the send timeout expires, the template throws `MessageDeliveryException`.

A successful send means the channel accepted the message under that channel's contract. It does not prove a consumer has finished processing, a business transaction has committed, or an external broker has persisted the message durably. Those guarantees depend on the channel implementation and adapter.

## 5. receiveAndConvert: Receiving a Message and Converting Its Payload

### 5.1. How It Works

`receiveAndConvert` receives a Message from a destination and then uses the converter to convert its payload to the requested type.

~~~java
OrderCreated event =
    template.receiveAndConvert(inboundChannel, OrderCreated.class);
~~~

A default destination can also be used:

~~~java
template.setDefaultDestination(inboundChannel);

OrderCreated event =
    template.receiveAndConvert(OrderCreated.class);
~~~

The `OrderCreated.class` argument indicates the desired Java type after conversion. The method returns the payload, not the entire Message. If you need to inspect headers such as correlation ID, content type, or timestamp, use `receive` to retrieve the `Message<?>` first.

### 5.2. Destination Must Support Polling

With `GenericMessagingTemplate`, the channel used for receiving must implement `PollableChannel`. An arbitrary `MessageChannel` cannot necessarily receive messages by polling.

`PollableChannel` provides:

- `receive()`: waits for a message without a time limit.
- `receive(timeout)`: waits at most the specified number of milliseconds.

If you pass a channel that only supports sending or only supports subscribers, `GenericMessagingTemplate` throws `IllegalStateException` stating that a `PollableChannel` is required.

### 5.3. When Is the Result null?

If no message arrives before the receive timeout finishes, the method returns `null`. Always check for null before using the payload:

~~~java
OrderCreated event =
    template.receiveAndConvert(inboundChannel, OrderCreated.class);

if (event == null) {
    // No message within the wait period.
    return;
}

handle(event);
~~~

A `null` result here indicates no message was received, for example due to timeout or interruption. If a message was received but the converter could not convert the payload to the target type, that is a conversion failure and must be handled via the corresponding exception.

## 6. convertSendAndReceive: Request-Reply with Conversion

### 6.1. How It Works

`convertSendAndReceive` combines three steps:

1. Convert the request object into a Message.
2. Send the request to the destination and wait for a reply.
3. Convert the reply's payload to the target class.

Example:

~~~java
PriceReply reply = template.convertSendAndReceive(
    priceRequestChannel,
    new PriceRequest("SKU-100"),
    PriceReply.class
);
~~~

The parameters are the destination, the request object, and the desired Java type for the reply. You can also pass headers or a `MessagePostProcessor` if you need metadata or request adjustments after conversion.

### 6.2. Reply Channel

Request-reply requires a return path. With `GenericMessagingTemplate`, the template creates a temporary reply channel for the exchange, attaches it to the request message, and waits for a reply. The handler receiving the request must send its reply to the reply channel provided in the request's headers.

General flow:

~~~text
Caller
  -> convertSendAndReceive(request)
  -> template creates request Message and temporary reply channel
  -> sends request to MessageChannel
  -> handler receives request
  -> handler creates reply Message and sends to replyChannel
  -> template receives reply
  -> converter converts payload to targetClass
  -> returns result to caller
~~~

If the handler only processes the request without sending a reply, the caller waits until the receive timeout expires. `convertSendAndReceive` is a synchronous operation: the calling thread blocks while waiting for the reply.

### 6.3. Timeouts and Late Replies

If no reply arrives before receive timeout, the method returns `null`. A reply can arrive after the caller has already timed out. By default, `GenericMessagingTemplate` logs a warning on late replies. You can configure:

~~~java
template.setThrowExceptionOnLateReply(true);
~~~

When this option is enabled, sending a late reply throws `MessageDeliveryException` on the reply-sending side. This option helps detect slow handlers or overly short timeouts.

Do not treat a timeout as proof that the request was not processed. The request may have reached the handler and the business logic may have completed, yet the reply did not arrive in time. If the caller retries, the business operation may execute twice; use a correlation ID and idempotency key when requests have business side effects.

## 7. Configuring Timeouts

`GenericMessagingTemplate` has two timeouts configured in milliseconds:

- `setSendTimeout(long)`: maximum time for send operations on channels supporting timeouts.
- `setReceiveTimeout(long)`: maximum time for receive operations and waiting for replies.

Example:

~~~java
GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setSendTimeout(1_000);
template.setReceiveTimeout(3_000);
~~~

In the current implementation, the default value of both timeouts is `-1`, meaning no time limit is set on the template. In that case, send or receive operations may wait indefinitely depending on the channel. Applications should consider setting finite timeouts to avoid holding threads unnecessarily.

With `GenericMessagingTemplate`, the two default headers `sendTimeout` and `receiveTimeout` can override the configured timeouts per message in request-reply operations. The template removes these two control headers before sending so they are not propagated as application metadata. Do not use them as business headers.

## 8. Choosing the Right Method

| Need | Method to Use | Reason |
|---|---|---|
| Already have a `Message<?>`, want to send as-is | `send` | Keeps control over payload and headers |
| Have a Java object and want to send it | `convertAndSend` | Template creates a Message via converter |
| Want to receive the full Message and headers | `receive` | Does not strip metadata |
| Want to receive the payload converted to a Java type | `receiveAndConvert` | Retrieves only the payload per target class |
| Both request and reply must remain raw Messages | `sendAndReceive` | Caller handles payload and headers directly |
| Send a request object and receive a reply object | `convertSendAndReceive` | Template converts both request and reply |

These methods are not interchangeable. Choose based on whether your code needs to work with the full Message or only the payload, and whether it needs to wait for a reply.

## 9. Service Usage Example

The following example illustrates the three operations inside a service. The channels and template are configured and managed by Spring; the snippet is an integration excerpt, not a standalone application.

~~~java
import java.util.Optional;

import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.core.GenericMessagingTemplate;

record OrderCreated(String orderId, int version) {}
record PriceRequest(String sku) {}
record PriceReply(String sku, long priceInCents) {}

final class OrderMessagingService {

    private final GenericMessagingTemplate template;
    private final MessageChannel orderEvents;
    private final PollableChannel inboundOrders;
    private final MessageChannel priceRequests;

    OrderMessagingService(
            GenericMessagingTemplate template,
            MessageChannel orderEvents,
            PollableChannel inboundOrders,
            MessageChannel priceRequests) {
        this.template = template;
        this.orderEvents = orderEvents;
        this.inboundOrders = inboundOrders;
        this.priceRequests = priceRequests;
    }

    void publish(OrderCreated event) {
        template.convertAndSend(orderEvents, event);
    }

    Optional<OrderCreated> pollNextOrder() {
        return Optional.ofNullable(
            template.receiveAndConvert(inboundOrders, OrderCreated.class)
        );
    }

    Optional<PriceReply> requestPrice(String sku) {
        return Optional.ofNullable(
            template.convertSendAndReceive(
                priceRequests,
                new PriceRequest(sku),
                PriceReply.class
            )
        );
    }
}
~~~

In the example:

- `publish` sends a payload without requesting a reply.
- `pollNextOrder` receives from a `PollableChannel`; `Optional.empty()` means no message arrived during the wait period.
- `requestPrice` sends a request and waits for a reply; `Optional.empty()` means no reply was received within the wait period.

If the application exchanges payloads in JSON format or across an out-of-process adapter, configure an appropriate converter and define the content type instead of relying on `SimpleMessageConverter`.

## 10. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Destination not found | Default destination not set or channel name cannot be resolved | Pass channel directly or configure a destination resolver |
| `MessageDeliveryException` on send | Channel rejected message or send timeout expired | Check channel capacity, subscribers, and send timeout |
| `IllegalStateException` on receive | Destination does not implement `PollableChannel` | Use a pollable channel or design subscriber-based receiving |
| `receiveAndConvert` returns `null` | No message before receive timeout | Check producer, channel, and wait duration |
| `convertSendAndReceive` returns `null` | Handler did not reply or reply arrived late | Check replyChannel, handler, and receive timeout |
| `MessageConversionException` | Converter does not support payload or target class | Configure appropriate converter and check content type |
| Caller thread blocked too long | Default timeout unlimited or set too high | Set finite timeouts and consider asynchronous processing |
| Reply arrives after timeout | Handler is slow or timeout is unsuitable | Measure latency, adjust timeout, and handle late replies |
| Business action runs twice after retry | Caller treated timeout as request not executed | Use correlation IDs, idempotency keys, and idempotent processing |

## 11. Safe Usage Principles

- Use `convertAndSend` when you only need to send a payload; use `send` when you have already built a Message and want to preserve its headers.
- Configure converters for the actual wire format; having "convert" in the method name does not mean it serializes to JSON by default.
- Use `PollableChannel` for synchronous receiving with `GenericMessagingTemplate`.
- Set send timeout and receive timeout aligned with your application's SLA.
- Handle `null` from receive and request-reply operations before using the result.
- Use `MessagePostProcessor` to add or adjust headers after conversion.
- Use `receive` or `sendAndReceive` when you need to inspect message headers.
- Design request-reply with correlation IDs and idempotency if requests have business side effects.
- Do not treat successful delivery to a channel as proof that the consumer committed the business operation.
- Do not use synchronous reply-waiting operations on event-handling or request threads that must not block for long.

## 12. References

- [Spring Framework — GenericMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html)
- [Spring Framework — AbstractMessageSendingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/AbstractMessageSendingTemplate.html)
- [Spring Framework — AbstractMessageReceivingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/AbstractMessageReceivingTemplate.html)
- [Spring Framework — AbstractMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/AbstractMessagingTemplate.html)
- [Spring Framework — MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [Spring Framework — SimpleMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/SimpleMessageConverter.html)
- [Spring Framework — PollableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html)
- [Spring Framework — MessagePostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessagePostProcessor.html)
