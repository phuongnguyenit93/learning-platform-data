# SIMP Headers and STOMP Native Headers When Sending

## 1. Two header layers in Spring Messaging

A message in Spring Messaging can carry two groups of metadata:

- **SIMP headers** are standardized metadata at the Spring layer, used for routing and message processing. Examples: `simpDestination`, `simpMessageType`, `simpSessionId`, `simpUser`, `simpSubscriptionId`, and `simpMessageId`.
- **STOMP native headers** are headers belonging to the STOMP protocol, held in a nested map under the `nativeHeaders` key (constant `NativeMessageHeaderAccessor.NATIVE_HEADERS`). Examples: `content-type`, `receipt`, `priority`, or custom application headers.

Both groups coexist in `MessageHeaders`, but they serve different purposes. SIMP headers describe the message according to the Spring model; native headers carry information at the STOMP protocol layer. A SIMP header does not automatically become a STOMP header, and a native header does not automatically become a Spring routing attribute.

## 2. Common SIMP headers

SIMP stands for Simple Messaging Protocol. This is Spring's message model, commonly encountered in WebSocket/STOMP applications.

| Header | Meaning |
|---|---|
| `simpDestination` | Logical destination, e.g., `/topic/updates` or `/queue/notifications`. |
| `simpMessageType` | Message type in Spring, e.g., `MESSAGE`, `SUBSCRIBE`. |
| `simpSessionId` | WebSocket/Spring session identifier when a user session exists. |
| `simpUser` | Principal associated with the session or message, if present. |
| `simpSubscriptionId` | Subscription identifier associated with the message. |
| `simpMessageId` | Message identifier managed by Spring, if set. |

When sending, the destination is usually represented by SIMP metadata. `SimpMessagingTemplate` and the broker use this metadata to process the message in Spring. Let Spring manage internal fields such as session, subscription, and message id; do not set them manually to spoof a session or subscription.

## 3. What are STOMP native headers?

STOMP is a frame-based messaging protocol. A frame has a command, headers, and a body. For example, a client sending a `SEND` frame can carry `destination`, `content-type`, `receipt`, and custom headers. When Spring receives a STOMP frame, protocol headers are stored in the native headers region so the application can read or forward them.

`NativeMessageHeaderAccessor` provides the main APIs:

- `setNativeHeader(name, value)`: sets a native header value.
- `addNativeHeader(name, value)`: appends a value; a single header can have multiple values.
- `getNativeHeader(name)`: retrieves the list of values.
- `toNativeHeaderMap()`: retrieves the native headers map.

Native header names are preserved as protocol names. For example, `setNativeHeader("x-trace-id", "abc-123")` creates the native header `x-trace-id`; it does not create a corresponding SIMP header.

## 4. Creating an outgoing message with both SIMP and native headers

Create an accessor for the Spring message, set the destination at the SIMP layer, and set protocol metadata with `setNativeHeader`:

```java
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.simp.SimpMessagingTemplate;

public class NotificationSender {
    private final SimpMessagingTemplate messagingTemplate;

    public NotificationSender(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void sendUpdate(String jsonPayload) {
        SimpMessageHeaderAccessor headers =
                SimpMessageHeaderAccessor.create(SimpMessageType.MESSAGE);

        // SIMP metadata: Spring uses destination for routing.
        headers.setDestination("/topic/updates");

        // Native metadata: belongs to the STOMP protocol layer.
        headers.setNativeHeader("x-event-type", "inventory-updated");
        headers.setNativeHeader("x-trace-id", "trace-123");

        // Allow the template to finalize headers when sending.
        headers.setLeaveMutable(true);

        messagingTemplate.convertAndSend(
                "/topic/updates",
                jsonPayload,
                headers.getMessageHeaders()
        );
    }
}
```

This is a server-side sending example. `SimpMessagingTemplate` must be configured in the messaging application, typically via `@EnableWebSocketMessageBroker`. The `/topic/updates` destination must align with broker configuration and authorization rules. The template's destination argument determines where to send; Spring manages the corresponding SIMP metadata.

If you need metadata used only internally within the Spring pipeline, you can use `setHeader("appCorrelationId", value)`. If you need a header represented at the STOMP layer, use `setNativeHeader("x-correlation-id", value)`. Choosing the right API determines which metadata region the header belongs to.

## 5. Reading native headers in a handler

In a handler receiving STOMP messages, you can wrap the message with an accessor to read native headers:

```java
import java.security.Principal;
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Controller;

@Controller
public class UpdateController {

    @MessageMapping("/updates")
    public void receive(Message<?> message, Principal principal) {
        SimpMessageHeaderAccessor accessor =
                SimpMessageHeaderAccessor.wrap(message);

        String traceId = accessor.getFirstNativeHeader("x-trace-id");
        String destination = accessor.getDestination();

        System.out.println("user=" +
                (principal != null ? principal.getName() : "anonymous"));
        System.out.println("destination=" + destination);
        System.out.println("traceId=" + traceId);
    }
}
```

In production code, process the payload according to the application's data types and validate input data. If a header has multiple values, use `getNativeHeader(name)` rather than taking only the first value. You can also accept `MessageHeaders` directly in the handler if the handler signature fits.

## 6. Choosing the right header type

| Need | How to represent |
|---|---|
| Set a Spring destination such as `/topic/orders` | SIMP destination (`setDestination` or the template's destination parameter). |
| Attach a trace id that must appear in the STOMP frame | Native header, e.g., `setNativeHeader("x-trace-id", id)`. |
| Store metadata for internal use only in the Spring pipeline | Custom header via `setHeader`. |
| Pass metadata per an agreed STOMP/client convention | Native header with the agreed name and format. |
| Identify user/session/subscription | Use Spring-managed authentication mechanisms and metadata; do not spoof with custom headers. |

Do not confuse the `destination` header in a STOMP frame with an arbitrary native header on a server-side message. When a client sends a STOMP frame, `destination` is an inbound protocol header and Spring maps it into the SIMP model. When the server sends via `SimpMessagingTemplate`, supply the destination to the template or accessor so Spring routes it.

## 7. Notes when sending

1. **Do not trust native headers from clients.** Clients can send arbitrary custom headers. Do not use `x-role`, `tenant-id`, or similar values as proof of authentication or authorization. Obtain identity from `Principal` and check permissions on the server.
2. **Avoid overwriting framework-managed headers.** Destination, session, subscription, and message id have internal meanings. Manually setting wrong values can break routing or produce inconsistent metadata.
3. **Headers can have multiple values.** STOMP allows repeated headers. Use list-based APIs when all values must be preserved; `getFirstNativeHeader` only retrieves the first value.
4. **Distinguish headers from payload.** Headers are suitable for short metadata like event type, trace id, or content type. Main business data should reside in the body so it has a clear schema.
5. **Do not assume every transport preserves native headers.** Across broker relays, external brokers, or other transports, preservation and forwarding depend on configuration and protocol.
6. **Follow naming conventions for headers.** Use a dedicated prefix such as `x-` or an application namespace to avoid colliding with standard STOMP headers and Spring headers.
7. **Control sensitive data.** Headers may appear in logs, tracing, or monitoring tools. Do not send tokens, passwords, or secrets in headers without proper protection in place.

## 8. Common mistakes

- **Using `setHeader` while expecting the header to appear in the STOMP frame:** `setHeader` sets Spring metadata. Use `setNativeHeader` for protocol headers.
- **Using `setNativeHeader` for routing:** a custom native header does not replace a SIMP destination. Set the destination via `setDestination` or the parameter of `convertAndSend`.
- **Reading from the wrong header region:** `MessageHeaders.get("x-trace-id")` looks up top-level keys; native headers live in the `nativeHeaders` map. Use `getFirstNativeHeader` or `getNativeHeader` through the accessor.
- **Assuming the broker understands custom headers:** a broker only processes headers according to the protocol or configuration it supports. Application headers are typically metadata agreed upon by both ends of the application.
- **Constructing identity from client headers:** headers are untrusted for authentication. Use Spring Security and `Principal`.

## 9. How to debug

When a message reaches the wrong destination or the client does not see a header, check in order:

1. Confirm that the destination passed to `SimpMessagingTemplate` has the right prefix and is configured to be handled by the broker.
2. Inspect SIMP metadata using `SimpMessageHeaderAccessor.wrap(message).getDestination()` and the corresponding message type.
3. Inspect native headers using `toNativeHeaderMap()` or `getNativeHeader("x-trace-id")`; do not inspect only the top-level keys of `MessageHeaders`.
4. Observe the actual STOMP frame on the client or in protocol logs to determine whether the header was serialized.
5. If using a broker relay, check broker behavior and relay configuration; do not infer forwarding solely from `MessageHeaders` contents inside the application.

## 10. Key takeaways

SIMP headers are metadata of the Spring Messaging model, especially useful for destinations and processing context. STOMP native headers are protocol metadata stored separately and can travel with STOMP frames. When sending, use the destination argument or `setDestination` for routing; use `setNativeHeader` for STOMP-layer metadata; use `setHeader` for internal Spring metadata. Choosing the right header layer ensures messages are routed properly, clients receive the intended metadata, and the application avoids improper coupling to protocol details.