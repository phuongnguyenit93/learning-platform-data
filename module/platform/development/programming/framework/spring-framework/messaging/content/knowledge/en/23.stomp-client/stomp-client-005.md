# StompFrameHandler and Converting Received Payloads

## Objectives

When a Java application uses Spring as a STOMP client, the client does not receive a Java object directly from the server. It receives a STOMP frame containing headers and a byte body. Spring provides `StompFrameHandler` to process received frames and `MessageConverter` to convert the body into the data type desired by the application.

The two core methods of `StompFrameHandler` are:

- `getPayloadType(StompHeaders headers)`: declares the target data type that the payload should be converted into.
- `handleFrame(StompHeaders headers, Object payload)`: processes the payload after the converter has converted it successfully.

This lesson uses `WebSocketStompClient` to illustrate a Java client receiving a JSON message and converting it into a DTO. The concepts of frame handlers and message converters also apply when using another Spring STOMP transport client.

## 1. Flow of receiving a STOMP frame

Once the client is STOMP-connected and subscribed to a destination, the broker can send a `MESSAGE` frame back to the client. The frame typically looks like this:

~~~text
MESSAGE
destination:/topic/prices
subscription:sub-0
message-id:msg-42
content-type:application/json

{"symbol":"ACME","price":125.50,"observedAtEpochMillis":1794033000000}
^@
~~~

A frame consists of a command, headers, and a body. In the example above:

- `MESSAGE` indicates the broker is delivering a message to a subscription.
- `destination` is the destination of the message.
- `subscription` identifies which subscription received the message.
- `message-id` is the message identifier provided by the broker.
- `content-type` describes the body format.
- The JSON section after the blank line is the message body.

Spring processes the frame through the following flow:

1. `WebSocketStompClient` receives the frame from the WebSocket transport.
2. Spring parses the command and STOMP headers into `StompHeaders`.
3. Spring looks up the handler attached to the corresponding subscription.
4. Spring calls `getPayloadType(headers)` to ask the handler which type it wants to receive.
5. The `MessageConverter` configured on the client converts the body from `byte[]` to the target type, based on the requested type and metadata such as `content-type`.
6. Spring invokes `handleFrame(headers, payload)` with the converted object.

Therefore, `handleFrame` usually does not need to read `byte[]` manually or call Jackson to parse JSON. Conversion is already performed before the callback if the client has an appropriate converter.

## 2. Role of StompFrameHandler

`StompFrameHandler` belongs to package `org.springframework.messaging.simp.stomp`. It is the contract for handling a STOMP frame delivered to a subscription.

~~~java
import java.lang.reflect.Type;
import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;

public class MyFrameHandler implements StompFrameHandler {

    @Override
    public Type getPayloadType(StompHeaders headers) {
        return String.class;
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        String text = (String) payload;
        System.out.println(text);
    }
}
~~~

`getPayloadType` is called before `handleFrame`. Its return type is `java.lang.reflect.Type`, allowing a concrete class type to be declared. For typical cases, return `String.class`, `byte[].class`, or a DTO class.

`handleFrame` receives two parameters:

- `headers`: the STOMP frame's metadata as `StompHeaders`.
- `payload`: the object converted by the converter to the type requested by `getPayloadType`. If the frame has no body, `payload` may be `null`.

A handler should check for null if the application protocol permits empty messages. If payloads can come from multiple sources or multiple schema versions, validate type and data before using them.

## 3. Choosing the right MessageConverter

`WebSocketStompClient` has a `MessageConverter` to convert payloads between Java objects and `byte[]` when sending or receiving. If no converter is configured, the client uses Spring's default converter; the default converter does not automatically turn arbitrary JSON into custom DTOs.

Common choices:

| Payload type | Converter | Return type from `getPayloadType` |
|---|---|---|
| Plain text | `StringMessageConverter` | `String.class` |
| Byte array | `ByteArrayMessageConverter` | `byte[].class` |
| JSON to DTO | `JacksonJsonMessageConverter` on Spring 7 | DTO class |
| JSON to DTO on Spring 6.x | `MappingJackson2MessageConverter` | DTO class |

Spring Framework 7 uses `JacksonJsonMessageConverter` based on Jackson 3. In Spring Framework 6.x, applications typically use `MappingJackson2MessageConverter` based on Jackson 2. `MappingJackson2MessageConverter` is marked deprecated starting in Spring 7.0 in favor of the new converter.

Configuration example for Spring Framework 7:

~~~java
import org.springframework.messaging.converter.JacksonJsonMessageConverter;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

WebSocketStompClient stompClient =
        new WebSocketStompClient(new StandardWebSocketClient());

stompClient.setMessageConverter(new JacksonJsonMessageConverter());
~~~

For Spring Framework 6.x, replace the converter configuration line with:

~~~java
import org.springframework.messaging.converter.MappingJackson2MessageConverter;

stompClient.setMessageConverter(new MappingJackson2MessageConverter());
~~~

The application must include the Jackson dependency matching the Spring version in use. The JSON converter also needs to receive an appropriate STOMP `content-type`, usually `application/json`. Client converter configuration and server/broker message format must align.

## 4. Converting JSON into a DTO

Suppose the server emits stock price data with a JSON body:

~~~json
{
  "symbol": "ACME",
  "price": 125.50,
  "observedAtEpochMillis": 1794033000000
}
~~~

Create a Java 17 DTO:

~~~java
import java.math.BigDecimal;

public record PriceUpdate(
        String symbol,
        BigDecimal price,
        long observedAtEpochMillis
) {
}
~~~

The handler declares the DTO as the target payload type:

~~~java
import java.lang.reflect.Type;
import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;

public class PriceUpdateFrameHandler implements StompFrameHandler {

    @Override
    public Type getPayloadType(StompHeaders headers) {
        return PriceUpdate.class;
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        if (payload == null) {
            System.out.println("Received an empty price update");
            return;
        }

        PriceUpdate update = (PriceUpdate) payload;

        System.out.println("Destination: " + headers.getDestination());
        System.out.println("Symbol: " + update.symbol());
        System.out.println("Price: " + update.price());
    }
}
~~~

When the frame has `content-type:application/json`, Spring uses the JSON converter to instantiate `PriceUpdate` before calling `handleFrame`. Inside the handler, `payload` is already a Java object so the record's accessors can be accessed directly.

This example uses epoch milliseconds to avoid requiring additional Jackson date-time module configuration. If the DTO uses `Instant`, `LocalDateTime`, or other Java Time types, ensure the corresponding Jackson Java Time module is installed and registered with the mapper.

## 5. Registering the handler when subscribing

The handler is passed to `StompSession.subscribe`. Subscribe after the STOMP session has connected successfully, usually inside the `afterConnected` callback:

~~~java
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;

public class PriceClientSessionHandler extends StompSessionHandlerAdapter {

    @Override
    public void afterConnected(
            StompSession session,
            org.springframework.messaging.simp.stomp.StompHeaders connectedHeaders) {

        session.subscribe(
                "/topic/prices",
                new PriceUpdateFrameHandler()
        );
    }
}
~~~

Here, `/topic/prices` is the destination the client wants to receive from. The handler attached to this subscription processes messages delivered by the broker to that subscription.

`subscribe` returns `StompSession.Subscription`. You can keep this handle to cancel the subscription when no longer needed:

~~~java
StompSession.Subscription subscription =
        session.subscribe("/topic/prices", new PriceUpdateFrameHandler());

// When stopping reception:
subscription.unsubscribe();
~~~

When subscribing to multiple destinations, you can create a separate handler per payload type. This clarifies each stream's schema and avoids having a single handler guess object types across many cases.

## 6. Complete client example with core components

The example below illustrates client configuration, connecting, and registering a handler. It assumes the server has exposed a STOMP endpoint at `/ws` and can emit JSON to `/topic/prices`.

~~~java
import org.springframework.messaging.converter.JacksonJsonMessageConverter;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

public class PriceClient {

    public static void main(String[] args) {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-client-");
        scheduler.initialize();

        WebSocketStompClient client =
                new WebSocketStompClient(new StandardWebSocketClient());

        client.setMessageConverter(new JacksonJsonMessageConverter());
        client.setTaskScheduler(scheduler);

        StompSessionHandlerAdapter sessionHandler =
                new StompSessionHandlerAdapter() {

            @Override
            public void afterConnected(
                    StompSession session,
                    org.springframework.messaging.simp.stomp.StompHeaders headers) {

                session.subscribe(
                        "/topic/prices",
                        new PriceUpdateFrameHandler()
                );
                System.out.println("Subscribed to /topic/prices");
            }

            @Override
            public void handleTransportError(
                    StompSession session,
                    Throwable exception) {
                System.err.println("STOMP transport error: " + exception.getMessage());
            }
        };

        client.connectAsync("ws://localhost:8080/ws", sessionHandler);
    }
}
~~~

In a real Spring application, declare `WebSocketStompClient` and `TaskScheduler` as beans and inject them into the component managing the connection. The example above focuses on connecting and registering the handler; the application lifecycle must manage closing the session, stopping the client, and shutting down the scheduler when the application terminates.

`StandardWebSocketClient` uses a Jakarta WebSocket-compatible implementation. If the runtime does not provide an implementation, add a suitable implementation to the classpath. You can replace the transport with a SockJS client when the server endpoint is configured with SockJS support.

## 7. Reading STOMP headers in handleFrame

Beyond the payload, the handler can read metadata for logging, routing inspection, or handling business headers:

~~~java
@Override
public void handleFrame(StompHeaders headers, Object payload) {
    String destination = headers.getDestination();
    String messageId = headers.getMessageId();
    var contentType = headers.getContentType();

    System.out.println("Destination: " + destination);
    System.out.println("Message ID: " + messageId);
    System.out.println("Content type: " + contentType);

    PriceUpdate update = (PriceUpdate) payload;
    System.out.println(update);
}
~~~

Commonly used accessors:

- `getDestination()`: the frame's destination.
- `getMessageId()`: message identifier if provided by the broker.
- `getSubscription()`: subscription identifier associated with the frame.
- `getContentType()`: MIME type of the payload.
- `getFirstNativeHeader(name)`: reads a native STOMP header added by the application.

Do not use client-sent custom headers as proof of authentication or access rights. Identity and permissions must be verified on the server through authentication/authorization mechanisms.

## 8. Selecting payload type by header

A subscription typically receives a uniform schema, so returning a fixed DTO from `getPayloadType` is the most maintainable choice.

If a destination intentionally carries multiple event types, a business header can be used to choose the type:

~~~java
@Override
public Type getPayloadType(StompHeaders headers) {
    String eventType = headers.getFirstNativeHeader("event-type");

    if ("PRICE_UPDATED".equals(eventType)) {
        return PriceUpdate.class;
    }

    return String.class;
}
~~~

The handler needs to process each corresponding type:

~~~java
@Override
public void handleFrame(StompHeaders headers, Object payload) {
    String eventType = headers.getFirstNativeHeader("event-type");

    if ("PRICE_UPDATED".equals(eventType) && payload instanceof PriceUpdate update) {
        handlePriceUpdate(update);
        return;
    }

    if (payload instanceof String text) {
        handleTextEvent(text);
        return;
    }

    throw new IllegalArgumentException("Unsupported event payload");
}
~~~

Both server and client must agree on header names, event type values, content type, and schemas. Do not select arbitrary classes solely based on untrusted data. With multiple event types, a common envelope DTO with `type` and `data` fields is often easier to evolve than constantly switching target types.

## 9. Handling String, byte[], and JSON payloads

**Plain text**

~~~java
@Override
public Type getPayloadType(StompHeaders headers) {
    return String.class;
}
~~~

Configure `StringMessageConverter` to receive text bodies:

~~~java
stompClient.setMessageConverter(new StringMessageConverter());
~~~

**Binary payloads**

~~~java
@Override
public Type getPayloadType(StompHeaders headers) {
    return byte[].class;
}
~~~

Configure `ByteArrayMessageConverter` if raw bytes must be processed. The application decodes the binary format itself after receiving the payload.

**JSON DTO**

~~~java
@Override
public Type getPayloadType(StompHeaders headers) {
    return PriceUpdate.class;
}
~~~

Use the Jackson converter appropriate for your Spring version. This is usually the most convenient approach for business applications because DTOs are strongly typed and easy to validate.

Do not parse JSON twice. If the converter has already returned `PriceUpdate`, do not convert that object back into a String to re-parse it with ObjectMapper.

## 10. Payload conversion errors and handling

| Symptom | Possible cause | What to check |
|---|---|---|
| `handleFrame` does not receive DTO | Client has not configured a JSON converter | Configure the converter matching the Spring version |
| No suitable converter found | STOMP `content-type` mismatch or unsupported payload type | Check `content-type` header and `getPayloadType` |
| Jackson reports parse error | Malformed JSON syntax or mismatch with DTO structure | Check actual body, field names, data types, and constructor/record |
| Type cast fails | `getPayloadType` returns a type different from what the handler casts to | Use a consistent target type and check with `instanceof` |
| Payload is null | Frame has no body | Handle empty case before casting |
| No frames received | Client not CONNECTED, not subscribed, or wrong destination | Check `afterConnected` callback, SUBSCRIBE, and broker destination |
| Large message rejected | Exceeds inbound buffer limit | Check `setInboundMessageSizeLimit` and transport/server limits |

When an exception occurs during frame processing or conversion, the session handler can receive details via `handleException`. Connection or transport errors are reported via `handleTransportError`. Log sufficient details such as destination, content type, and error category; avoid logging tokens, passwords, or sensitive data inside payloads.

Example adding error callbacks:

~~~java
@Override
public void handleException(
        StompSession session,
        StompCommand command,
        StompHeaders headers,
        byte[] payload,
        Throwable exception) {

    System.err.println("STOMP handling error: " + exception.getMessage());
}

@Override
public void handleTransportError(
        StompSession session,
        Throwable exception) {

    System.err.println("Transport error: " + exception.getMessage());
}
~~~

## 11. Heartbeats, receipts, and message size

**Heartbeats** help detect inactive connections. `WebSocketStompClient` can use a `TaskScheduler` to schedule heartbeats. When a scheduler is configured, the client uses appropriate default heartbeats instead of disabling client default heartbeats. The scheduler is also required for receipt tracking.

**Receipts** confirm that the broker has processed a STOMP operation such as SEND or SUBSCRIBE. Automatic receipts can be enabled:

~~~java
session.setAutoReceipt(true);

session.subscribe("/topic/prices", new PriceUpdateFrameHandler())
        .addReceiptTask(() -> System.out.println("SUBSCRIBE processed"));
~~~

A receipt confirms the broker processed the frame; it does not prove logic inside `handleFrame` has completed or that the user has seen the information.

**Message size**: the default inbound message limit of `WebSocketStompClient` is 64 KB. It can be increased or decreased as needed:

~~~java
stompClient.setInboundMessageSizeLimit(128 * 1024);
~~~

This limit must be coordinated with WebSocket container, reverse proxy, and broker limits. Do not raise limits arbitrarily; large payloads increase memory and processing cost per connection.

## 12. Testing handlers and converters

There are two levels of testing:

1. **Handler unit tests**: pass DTOs and headers directly to `handleFrame` to test processing logic. This does not verify JSON deserialization.
2. **Integration tests**: run the STOMP client against a real server/broker or suitable test broker, send a JSON frame with `content-type:application/json`, and verify the callback receives the expected DTO.

Scenarios to verify:

- Valid JSON is converted into the right DTO.
- Malformed body produces an observable conversion error via the session handler.
- Empty body is handled according to application rules.
- Unsupported content-type header is detected.
- Subscribing to the right destination receives messages.
- Unsubscribing prevents the handler from receiving subsequent messages.
- Connection loss is reported via `handleTransportError`.

A unit test calling `handleFrame` directly cannot prove `MessageConverter` is configured properly. To test conversion, test through the STOMP client's frame-receiving pipeline.

## Takeaways

- `StompFrameHandler` processes frames delivered to a subscription.
- `getPayloadType` declares the target type and is called before `handleFrame`.
- `MessageConverter` converts the body from `byte[]` to a Java object based on the target type and headers such as `content-type`.
- `handleFrame` receives the converted payload; `payload` can be null if the body is empty.
- Use `StringMessageConverter` for text, `ByteArrayMessageConverter` for bytes, and a Jackson converter for JSON DTOs.
- Spring 7 uses `JacksonJsonMessageConverter` (Jackson 3); Spring 6.x commonly uses `MappingJackson2MessageConverter` (Jackson 2).
- Register subscriptions after STOMP CONNECTED, typically inside `afterConnected`.
- Use `handleException` and `handleTransportError` to observe processing and transport errors.
- Receipts confirm the broker processed a frame, not that business processing is complete.

## References

- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/client.html)
- [StompFrameHandler API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/simp/stomp/StompFrameHandler.html)
- [StompSession API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.html)
- [WebSocketStompClient API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html)
- [JacksonJsonMessageConverter API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/converter/JacksonJsonMessageConverter.html)
