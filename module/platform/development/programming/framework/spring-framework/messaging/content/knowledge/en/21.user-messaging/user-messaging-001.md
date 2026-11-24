# SimpMessageSendingOperations and SimpMessagingTemplate

## Objectives

In Spring Messaging, `SimpMessageSendingOperations` and `SimpMessagingTemplate` provide the API for sending messages to a destination in a messaging system. When an application uses STOMP over WebSocket, these two components are commonly used to send data from a service, event listener, or controller to connected clients.

This lesson focuses on sending private messages to a single user: how to choose between the interface and the implementation, how routing works with user destinations, broker configuration, passing headers, and handling common errors.

After this lesson, you can:

- Explain the relationship between `SimpMessageSendingOperations` and `SimpMessagingTemplate`.
- Send a message to a shared destination using `convertAndSend`.
- Send a message to a specific user using `convertAndSendToUser`.
- Configure and use `/user/queue/...` destinations in STOMP.
- Choose the right user identity, pass headers, and troubleshoot message-sending errors.

## 1. Background: messages, channels, and destinations

Spring Messaging models data sent in an application using `Message<T>`. A message consists of a payload and headers:

- **Payload** is the business data, such as a `Notification`, `OrderStatus`, or a text string.
- **Headers** contain metadata such as destination, content type, session ID, and protocol native headers.
- **MessageChannel** is the channel for passing messages between components in the system.
- **MessageConverter** converts Java objects into a data format that the protocol or client can receive, typically JSON when Jackson is configured in the application.

In STOMP over WebSocket, a destination is the logical target name that clients subscribe to or the server sends to. Some common destinations:

| Destination | Common purpose |
| --- | --- |
| `/topic/...` | A group of subscribers receiving the same stream of messages, typically used for broadcasting |
| `/queue/...` | A queue-style message stream or specific recipient point, depending on the broker |
| `/user/queue/...` | A logical destination dedicated to the currently logged-in user |
| `/app/...` | Prefix for messages sent by clients to `@MessageMapping` methods |

A destination is only a routing address. It does not authenticate the sender on its own, does not grant access permissions, and does not guarantee that the client has read the message.

## 2. What is `SimpMessageSendingOperations`?

`SimpMessageSendingOperations` belongs to the package:

```java
org.springframework.messaging.simp.SimpMessageSendingOperations
```

This is an **interface** that specializes `MessageSendingOperations<String>` for Spring's simple messaging model, including STOMP support. The generic parameter `String` indicates that destinations are represented as strings.

This interface inherits general sending operations such as:

- `convertAndSend(destination, payload)`: converts a payload object into a message and sends it to the destination.
- Overloads of `convertAndSend` that additionally accept headers or a `MessagePostProcessor`.
- `send(message)`: sends a pre-built `Message<?>`, typically requiring a destination header.

An important distinguishing feature of `SimpMessageSendingOperations` is the `convertAndSendToUser(...)` family of overloads. This group of methods allows sending a message to a user through Spring's user destination mechanism.

### `convertAndSendToUser` overloads

The main overloads include:

```java
void convertAndSendToUser(
        String user, String destination, Object payload);

void convertAndSendToUser(
        String user, String destination, Object payload,
        Map<String, Object> headers);

void convertAndSendToUser(
        String user, String destination, Object payload,
        MessagePostProcessor postProcessor);

void convertAndSendToUser(
        String user, String destination, Object payload,
        Map<String, Object> headers,
        MessagePostProcessor postProcessor);
```

Parameter meanings:

| Parameter | Meaning |
| --- | --- |
| `user` | The user name that Spring uses to look up the corresponding WebSocket sessions |
| `destination` | The target destination inside the user destination, for example `/queue/notifications` |
| `payload` | The object to send; it can be converted by a message converter |
| `headers` | Additional metadata for the message |
| `postProcessor` | Callback to modify the message after it is created and before it is sent |

`user` must match the identity that Spring attaches to the WebSocket session. For typical authenticated applications, that value is usually `Principal.getName()`.

API call example:

```java
messagingOperations.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        notification
);
```

For user `alice`, Spring resolves the destination according to the configured user destination prefix, which defaults to `/user/`. Alice's client subscribes to:

```javascript
stompClient.subscribe("/user/queue/notifications", (frame) => {
    const notification = JSON.parse(frame.body);
    console.log(notification);
});
```

On the server side, pass the destination `/queue/notifications` to `convertAndSendToUser`. The client subscribes to `/user/queue/notifications`. Do not manually prepend `/user/alice` to the `destination` parameter when calling this method; the user prefix and user name are handled by the template.

## 3. What is `SimpMessagingTemplate`?

`SimpMessagingTemplate` is the **implementation** of `SimpMessageSendingOperations`. This class belongs to the package:

```java
org.springframework.messaging.simp.SimpMessagingTemplate
```

The template acts as a facade to send messages into the message channel that Spring STOMP configures for the broker. It inherits payload conversion and message-sending mechanisms from `AbstractMessageSendingTemplate<String>`, while implementing operations specific to the simple messaging protocol.

Key characteristics to remember:

- The constructor takes a `MessageChannel`.
- The default user destination prefix is `/user/`.
- The send timeout can be configured via `setSendTimeout(long)`.
- A `MessageHeaderInitializer` can be configured to initialize headers for messages created through the template.
- Provides `convertAndSend`, `convertAndSendToUser`, and `send`.

In a Spring application with a STOMP message broker enabled, Spring creates and manages the corresponding template. The bean is usually named `brokerMessagingTemplate`. Normally, you should inject the bean via Spring rather than manually creating `new SimpMessagingTemplate(...)`, because the template needs the exact message channel managed by the messaging configuration.

### Should you inject the interface or the class?

In business services, prefer injecting `SimpMessageSendingOperations`:

```java
@Service
public class NotificationSender {

    private final SimpMessageSendingOperations messaging;

    public NotificationSender(
            SimpMessageSendingOperations messaging) {
        this.messaging = messaging;
    }
}
```

This keeps the service depending on the message-sending contract. When you need specific configuration available only on `SimpMessagingTemplate`, or need to call implementation-specific APIs, you can inject `SimpMessagingTemplate` directly.

If there are multiple beans in the ApplicationContext implementing the interface, use `@Qualifier` to specify the bean. With a standard STOMP configuration, the bean name created by Spring is typically `brokerMessagingTemplate`.

## 4. Configuring STOMP user destinations

For `convertAndSendToUser` to work, the application must enable a STOMP message broker and configure appropriate destination prefixes.

Java configuration example:

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(
            MessageBrokerRegistry registry) {

        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
```

Each configuration has a distinct role:

- `registerStompEndpoints`: registers the HTTP/WebSocket endpoint for clients to initiate connections, here `/ws`.
- `setApplicationDestinationPrefixes("/app")`: specifies the prefix for messages from clients routed to `@MessageMapping` handlers.
- `enableSimpleBroker("/topic", "/queue")`: enables the simple broker to handle the declared destinations.
- `setUserDestinationPrefix("/user")`: declares the prefix that `UserDestinationMessageHandler` uses to recognize user destinations.

In this example, clients can send messages to `/app/...`, subscribe to broadcasts at `/topic/...`, or subscribe to private destinations at `/user/queue/...`.

The simple broker is suitable for applications and loads within its capabilities. When an independent broker or infrastructure-level scalability is needed, a STOMP broker relay can be configured. The user destination mechanism still needs to be routed properly in both cases.

## 5. Message-sending flow to a user

Suppose Alice has logged in and the WebSocket handshake creates a `Principal` whose `getName()` returns `"alice"`.

The message-sending flow can be visualized as follows:

1. Alice's client connects to the `/ws` endpoint.
2. The client subscribes to `/user/queue/notifications`.
3. A service in the application needs to send a notification to Alice.
4. The service calls `convertAndSendToUser("alice", "/queue/notifications", payload)`.
5. `SimpMessagingTemplate` creates the message and sends it to the broker channel.
6. `UserDestinationMessageHandler` resolves the user destination into an actual destination bound to Alice's session.
7. The broker forwards the message to sessions subscribed to the corresponding destination.

`/user/queue/notifications` is a logical destination. Spring resolves it into a session-specific destination so that two users can both subscribe to `/user/queue/notifications` without receiving each other's messages.

If a user has multiple WebSocket sessions, by default the user destination targets the corresponding sessions of that user. This differs from sending to a single session ID.

## 6. Usage example from a service

### DTO

Use a Java 17 record to represent a notification:

```java
import java.time.Instant;

public record Notification(
        String id,
        String message,
        Instant createdAt
) {
}
```

### Notification-sending service

```java
import org.springframework.messaging.simp.SimpMessageSendingOperations;
import org.springframework.stereotype.Service;

@Service
public class NotificationSender {

    private final SimpMessageSendingOperations messaging;

    public NotificationSender(
            SimpMessageSendingOperations messaging) {
        this.messaging = messaging;
    }

    public void sendToUser(
            String username,
            Notification notification) {

        messaging.convertAndSendToUser(
                username,
                "/queue/notifications",
                notification
        );
    }
}
```

When another service needs to notify the user:

```java
notificationSender.sendToUser(
        "alice",
        new Notification(
                "notice-1001",
                "Your order has been confirmed.",
                Instant.now()
        )
);
```

If the application is handling a request or message that has a `Principal`, obtain the user from the security context or from the `Principal` provided by Spring. For example, inside a `@MessageMapping` method:

```java
@MessageMapping("/orders")
public void handleOrder(
        OrderRequest request,
        Principal principal) {

    // Process business logic and create notification.
    Notification notification = new Notification(
            "order-confirmed",
            "Your order has been confirmed.",
            Instant.now()
    );

    notificationSender.sendToUser(
            principal.getName(),
            notification
    );
}
```

The example above illustrates obtaining the user from an authenticated connection. In a real application, handle the case where `principal` does not exist according to the application's authentication policy.

## 7. Sending to a shared destination vs. sending to a user

Use `convertAndSend` when all clients subscribed to the same destination should receive the message:

```java
messaging.convertAndSend(
        "/topic/system-announcements",
        announcement
);
```

Use `convertAndSendToUser` when the message is intended only for the target user:

```java
messaging.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        notification
);
```

Comparison:

| Criterion | `convertAndSend` | `convertAndSendToUser` |
| --- | --- | --- |
| Address | Regular destination | User and destination |
| Purpose | Broadcast or send to a group of subscribers | Send privately by user identity |
| Server example | `/topic/news` | User `alice`, `/queue/notifications` |
| Client subscribe example | `/topic/news` | `/user/queue/notifications` |
| User resolution mechanism | No | Yes, via user destination handler |

Do not send private data to `/topic/...` if multiple clients can subscribe to that destination.

## 8. Passing headers and processing messages before sending

The overloads accepting `headers` are useful when you need to add metadata to a message. For example, you can set the content type or a native STOMP header.

Prefer `SimpMessageHeaderAccessor` when you want to build Spring messaging headers explicitly:

```java
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.util.MimeTypeUtils;

SimpMessageHeaderAccessor accessor =
        SimpMessageHeaderAccessor.create();

accessor.setContentType(MimeTypeUtils.APPLICATION_JSON);
accessor.setNativeHeader("trace-id", traceId);
accessor.setLeaveMutable(true);

MessageHeaders headers = accessor.getMessageHeaders();

messaging.convertAndSendToUser(
        username,
        "/queue/notifications",
        notification,
        headers
);
```

Notes on headers:

- With a plain `Map<String, Object>`, `SimpMessagingTemplate` by default interprets the entries as native headers and places them under the `nativeHeaders` key.
- If the map already contains the `nativeHeaders` key, or if headers were created with `SimpMessageHeaderAccessor`, the template uses the headers in that structure.
- `setContentType` sets the content type at the Spring message level; `setNativeHeader` sets a protocol native header.
- The message converter must support the payload type and content type being used.

You can use a `MessagePostProcessor` to modify the message after the template creates it but before it is sent:

```java
messaging.convertAndSendToUser(
        username,
        "/queue/notifications",
        notification,
        message -> {
            // Appropriate headers can be added or adjusted here.
            return message;
        }
);
```

A post-processor should only perform necessary metadata changes; avoid placing complex business logic inside this callback.

## 9. When a session does not have an authenticated user

Normally, `user` passed to `convertAndSendToUser` is the name of the authenticated user attached to the WebSocket session. Spring also supports sessions without an authenticated principal: the session ID can be used as the `user` value, provided that headers containing the corresponding `sessionId` are passed.

Advanced example:

```java
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;

SimpMessageHeaderAccessor accessor =
        SimpMessageHeaderAccessor.create();

accessor.setSessionId(sessionId);
accessor.setLeaveMutable(true);

MessageHeaders headers = accessor.getMessageHeaders();

messaging.convertAndSendToUser(
        sessionId,
        "/queue/replies",
        payload,
        headers
);
```

This approach targets a known session. It does not replace authentication and authorization mechanisms. Only use a session ID when the application has a trustworthy basis to identify the target session.

## 10. `@SendToUser` and `convertAndSendToUser`

Spring also provides the `@SendToUser` annotation for message-handling methods. This annotation is suitable when you want to send the return value of a `@MessageMapping` method to the user who sent the message.

Example:

```java
@Controller
public class PortfolioController {

    @MessageMapping("/trade")
    @SendToUser("/queue/position-updates")
    public TradeResult executeTrade(Trade trade) {
        return tradeService.execute(trade);
    }
}
```

You can configure `broadcast = false` when you only want to send the reply to the session that sent the message:

```java
@MessageExceptionHandler
@SendToUser(
        destinations = "/queue/errors",
        broadcast = false
)
public ApplicationError handleException(
        MyBusinessException exception) {

    return new ApplicationError(exception.getMessage());
}
```

Distinguishing the two approaches:

- `@SendToUser`: declares the destination directly on the method; Spring sends the return value to the user associated with the message currently being processed.
- `convertAndSendToUser`: proactively sends a message from any component that has access to messaging operations, such as a service, event listener, or scheduled task.

Use the annotation when the message is a direct reply from a handler. Use the template when the sending time or origin of the message lies outside the `@MessageMapping` processing flow.

## 11. Testing message-sending services

You can unit test the service by mocking `SimpMessageSendingOperations`, then verifying that the service invokes it with the expected user, destination, and payload.

Example with JUnit 5 and Mockito:

```java
@ExtendWith(MockitoExtension.class)
class NotificationSenderTest {

    @Mock
    private SimpMessageSendingOperations messaging;

    private NotificationSender sender;

    @BeforeEach
    void setUp() {
        sender = new NotificationSender(messaging);
    }

    @Test
    void sendsNotificationToExpectedUserDestination() {
        Notification notification = new Notification(
                "notice-1001",
                "Your order has been confirmed.",
                Instant.parse("2026-01-01T10:00:00Z")
        );

        sender.sendToUser("alice", notification);

        verify(messaging).convertAndSendToUser(
                "alice",
                "/queue/notifications",
                notification
        );
    }
}
```

This test verifies the API call logic at the service layer. It does not prove that the WebSocket handshake, user destination resolution, broker routing, or client subscription work. To test the entire flow, an integration test with the messaging infrastructure and a suitable STOMP client is required.

## 12. Common errors and troubleshooting

### User does not receive the message

Check in order:

1. Does the `username` passed in match `Principal.getName()` of the WebSocket session?
2. Did the client subscribe to `/user/queue/notifications` correctly?
3. Did the server pass the destination `/queue/notifications` to `convertAndSendToUser`?
4. Is `setUserDestinationPrefix("/user")` configured consistently?
5. Does the broker handle the `/queue` prefix or the corresponding destination?
6. Does the user have an active connected session and valid subscription?

`convertAndSendToUser` is not an offline storage queue. If the user has no matching session, the message may not reach the client. If persistent notifications are needed, store notifications in a database or use a separate storage/message delivery mechanism and sync when the user reconnects.

### Wrong destination or duplicated prefix

With the `/user` prefix configuration, the call:

```java
messaging.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        payload
);
```

already provides the correct destination to the API. Do not pass `/user/alice/queue/notifications` as the `destination` parameter, because the API already takes `user` separately and handles the user destination prefix itself.

### User receives messages across multiple tabs or devices

By default, a user destination can be resolved to all active sessions of the same user. If a business requirement states that it should only be sent to a single session, you must design specific session routing and manage session IDs safely. For replies within a message-handling flow, `@SendToUser(broadcast = false)` is the option targeting the session that sent the message.

### Broker treats `/user/...` as a regular destination

Check the user destination prefix and broker configuration. The `/user` prefix needs to be handled by Spring's user destination handler. The broker should be configured with actual prefixes such as `/topic` and `/queue`, rather than directly receiving the `/user` prefix as a regular broker destination.

### Send failure or timeout

Send operations can throw a `MessagingException` or errors related to the message channel. `SimpMessagingTemplate` provides `setSendTimeout(long)` to configure the send timeout in milliseconds. Inspect the logs and channel/broker status when errors occur. A successful send call also does not mean the client has received, displayed, or processed the payload.

### Malformed message

Check the message converter, payload type, and content type. If the client expects JSON, ensure the application has a suitable JSON converter and the payload is serializable. When passing headers, distinguish between Spring message headers and native STOMP headers.

## 13. Practical usage guidelines

- Inject `SimpMessageSendingOperations` into services to reduce coupling to the implementation.
- Use `Principal.getName()` or a server-authenticated identity as the user key; do not trust an arbitrary username sent by the client.
- Use `convertAndSendToUser` for private messages and `convertAndSend` for broadcasts.
- Ensure clients subscribe to the right user destination and the broker is configured with the right prefixes.
- Only include data that the target user is authorized to view in the payload; destinations are not an authorization layer.
- Keep payloads clear, structured, and compatible with the message converter.
- For important notifications requiring guaranteed storage, retry, or review, store state in the business system; WebSocket should only serve as the realtime push channel.
- Monitor channel errors, broker errors, and connection states; do not treat a `convertAndSendToUser` call as proof that the client processed the message.
- When using an external broker, check the cleanup policy for destinations/queues created for inactive user sessions.

## 14. Summary

`SimpMessageSendingOperations` is the abstraction for sending messages by destination and user destination in Spring Messaging. `SimpMessagingTemplate` is the implementation typically configured and provided by Spring for STOMP applications.

For sending private messages to a single user, the core call pattern is:

```java
messaging.convertAndSendToUser(
        principal.getName(),
        "/queue/notifications",
        notification
);
```

The client subscribes to the logical destination:

```javascript
stompClient.subscribe("/user/queue/notifications", onNotification);
```

Spring uses the user destination handler to resolve the logical destination into a private destination for the corresponding sessions. For this flow to work, the STOMP broker, user destination prefix, user identity, and client subscription must be configured consistently.

## References

- [Spring Framework Reference — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework Reference — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
- [Spring Framework Javadoc — SimpMessageSendingOperations](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/SimpMessageSendingOperations.html)
- [Spring Framework Javadoc — SimpMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/SimpMessagingTemplate.html)
