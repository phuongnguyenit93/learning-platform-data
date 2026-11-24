# Separating Application Send Permissions from Broker Read Permissions

## Learning Objectives

After this article, you will be able to:

- Distinguish STOMP `MESSAGE` (sending data) from `SUBSCRIBE` (subscribing to receive data).
- Explain why permission to send to application destinations `/app/**` must be separated from permission to subscribe to broker destinations `/topic/**` or `/queue/**`.
- Configure Spring Security using `AuthorizationManager<Message<?>>`, `simpMessageDestMatchers`, and `simpSubscribeDestMatchers`.
- Block clients from sending directly to broker destinations to prevent spoofing server-emitted messages.
- Grant subscribe permissions only to the data streams a user is authorized to read.
- Test allowed and denied cases while understanding the roles of authentication, CSRF, and business-level permission checks.

## 1. Why must send permissions and read permissions be separated?

In a WebSocket application using STOMP, a client can perform multiple types of operations on a destination:

- Send a `SEND` frame to a destination.
- Send a `SUBSCRIBE` frame to receive messages from a destination.

Spring translates these two operations into different message types in the messaging system:

| STOMP frame | Spring message type | Meaning |
|---|---|---|
| `SEND` | `SimpMessageType.MESSAGE` | Client sends a payload to the server or broker |
| `SUBSCRIBE` | `SimpMessageType.SUBSCRIBE` | Client subscribes to receive messages |
| `UNSUBSCRIBE` | `SimpMessageType.UNSUBSCRIBE` | Client unsubscribes |
| `CONNECT` | `SimpMessageType.CONNECT` | Client initiates a STOMP session |
| `DISCONNECT` | `SimpMessageType.DISCONNECT` | Client terminates a STOMP session |

The two operations `MESSAGE` and `SUBSCRIBE` have different security purposes. A user being allowed to send a command to create an order does not mean that user is allowed to read every topic in the system. Likewise, a user being allowed to follow notifications in a topic does not mean that user is allowed to publish data into that topic.

For example:

- The client sends chat content to `/app/chat.send`. Spring routes the message to a controller with `@MessageMapping`.
- The client subscribes to `/topic/chat/room-42` to receive messages for the chat room.
- The server sends data to `/topic/chat/room-42` after completing business processing.

Permissions need to be separated into two questions:

1. Is the user allowed to **send commands to the application** via `/app/**`?
2. Is the user allowed to **subscribe to read data** from a specific broker destination?

If you only check a generic prefix or only require the user to be logged in, the application may inadvertently let clients send messages to destinations the server reserves for the broker, or let users read data outside their scope.

## 2. Application destinations and broker destinations

A STOMP configuration typically distinguishes three prefix groups:

| Prefix | Role | Example |
|---|---|---|
| `/app` | Destinations for messages entering application controllers | `/app/chat.send` |
| `/topic`, `/queue` | Destinations handled by the message broker | `/topic/chat/room-42`, `/queue/notifications` |
| `/user` | User destinations resolved by Spring per Principal/session | `/user/queue/notifications` |

A broker configuration might look like this:

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

Flow for sending to the application:

```text
Client -- SEND /app/chat.send --> Spring clientInboundChannel
                                  |
                                  v
                         @MessageMapping("/chat.send")
                                  |
                                  v
                          Business processing
                                  |
                                  v
                         BrokerChannel / Broker
                                  |
                                  v
                      MESSAGE /topic/chat/room-42
```

Flow for reading from the broker:

```text
Client -- SUBSCRIBE /topic/chat/room-42 --> Spring clientInboundChannel
                                             |
                                             v
                                       Security check
                                             |
                                             v
                                      BrokerChannel
                                             |
                                             v
                                      Subscription
                                             |
                                             v
                              Receive messages sent by the server
```

`/app/**` usually represents commands or data sent by the client to the application. `/topic/**` and `/queue/**` usually represent data streams distributed by the broker. However, prefixes are only routing conventions; actual permissions must be configured using explicit matchers and authorities.

An important point: a client can also send `SEND` directly to a broker destination such as `/topic/chat/room-42`. If the application permits this operation, the client can broadcast messages directly to subscribers without going through the controller, validation, or business permission checks that the server intends to enforce.

Therefore, in many applications, clients may only send `MESSAGE` to `/app/**`; `MESSAGE` frames to `/topic/**` or `/queue/**` are denied. Clients may be allowed to `SUBSCRIBE` to designated topics/queues.

## 3. Two permission types to manage separately

### Permission to send to application destinations

This permission controls STOMP `SEND` frames translated into `MESSAGE` messages whose destination falls under `/app/**`.

Examples:

- `chat:send`: allowed to send chat commands.
- `order:create`: allowed to send order creation commands.
- `support:reply`: allowed to send replies to the support system.

This permission only allows the message to enter the matching application handler. Controllers and services must still validate the payload, resource ownership, and business conditions.

### Permission to read from broker destinations

This permission controls STOMP `SUBSCRIBE` frames translated into `SUBSCRIBE` messages.

Examples:

- `chat:read`: allowed to subscribe to chat topics.
- `order:events:read`: allowed to read order events.
- `notification:read`: allowed to receive private notifications.

Read permissions must also account for the specific destination. Having `chat:read` does not mean a user can subscribe to all chat topics if the application has private rooms. For sensitive data, membership or per-resource permissions must be checked.

### Sample authorization table

| Operation | Destination | Authority | Result |
|---|---|---|---|
| `MESSAGE` | `/app/chat/**` | `chat:send` | Allow |
| `SUBSCRIBE` | `/topic/chat/**` | `chat:read` | Allow |
| `SUBSCRIBE` | `/user/queue/notifications` | `notification:read` | Allow |
| `MESSAGE` | `/topic/chat/**` | Any | Deny |
| `MESSAGE` | `/queue/**` | Any | Deny |
| `SUBSCRIBE` | `/queue/**` | Any | Deny per example policy |
| `SUBSCRIBE` | `/app/**` | Any | Deny |
| Undeclared destination or message type | Any | Any | Deny by default |

This table illustrates a sample policy. An application may add public destinations or other permissions, but each exception should have a clear business reason.

## 4. Configuring with AuthorizationManager

Since Spring Security 5.8, message security can be configured using the `AuthorizationManager` API. With Spring Security 6.x/7.x, you can use `@EnableWebSocketSecurity` and expose an `AuthorizationManager<Message<?>>` bean.

Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class WebSocketSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            // CONNECT, DISCONNECT, and messages without a destination.
            .nullDestMatcher().authenticated()

            // Only allow MESSAGE sent to application handlers.
            .simpMessageDestMatchers("/app/chat/**")
                .hasAuthority("chat:send")

            // Do not allow clients to publish directly to broker destinations.
            .simpMessageDestMatchers("/topic/**", "/queue/**")
                .denyAll()

            // Only allow reading chat topics with the chat:read authority.
            .simpSubscribeDestMatchers("/topic/chat/**")
                .hasAuthority("chat:read")

            // Private user destination requires notification read authority.
            .simpSubscribeDestMatchers("/user/queue/notifications")
                .hasAuthority("notification:read")

            // Do not allow subscribing directly to physical queues.
            .simpSubscribeDestMatchers("/queue/**")
                .denyAll()

            // Any MESSAGE or SUBSCRIBE without a specific rule is denied.
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()

            // All remaining message types are also denied unless declared.
            .anyMessage().denyAll();

        return messages.build();
    }
}
```

Key matchers:

- `nullDestMatcher()` matches messages without a destination, such as `CONNECT`, `DISCONNECT`, `UNSUBSCRIBE`, and certain control messages. The example requires an authenticated user.
- `simpMessageDestMatchers(...)` matches only `SimpMessageType.MESSAGE` with the corresponding destination.
- `simpSubscribeDestMatchers(...)` matches only `SimpMessageType.SUBSCRIBE` with the corresponding destination.
- `simpTypeMatchers(...)` matches by message type regardless of destination.
- `anyMessage()` is the catch-all matcher for any message.

Rules are evaluated in declaration order; the first matching rule determines the decision. Therefore, specific allow rules must be placed before broad deny rules. `anyMessage().denyAll()` ensures the system rejects unforeseen message types when new destinations or features are added.

### Why use simpMessageDestMatchers?

`MESSAGE` and `SUBSCRIBE` are two distinct actions, even when they share a destination. `simpMessageDestMatchers` scopes the rule to sending operations. `simpSubscribeDestMatchers` scopes the rule to subscription operations.

If you use a destination matcher that does not restrict the message type, a rule may apply more broadly than intended. Using separate matchers by message type makes the policy easier to read and audit.

## 5. Reading the policy rule by rule

### 5.1. Requiring authentication for messages without a destination

```java
.nullDestMatcher().authenticated()
```

Certain control frames such as `CONNECT`, `DISCONNECT`, or `UNSUBSCRIBE` do not carry a destination. This rule requires an authenticated user for that group of messages.

`@EnableWebSocketSecurity` also enables CSRF protection for inbound `CONNECT` under the default configuration. Clients must send a valid CSRF token in the STOMP headers when connecting. This helps reduce the risk of Cross-Site WebSocket Hijacking attacks.

If the application permits anonymous connections, you must design specific rules for destinationless messages and restrict which operations anonymous users can perform. You should not broadly drop authentication requirements just to let a client connect.

### 5.2. Allowing commands to be sent to controllers

```java
.simpMessageDestMatchers("/app/chat/**")
    .hasAuthority("chat:send")
```

Only `SEND` frames whose destination matches `/app/chat/**` are handled by this rule. The user needs the `chat:send` authority.

Examples:

- `SEND /app/chat.send` — may be allowed if the matcher and authority match.
- `SUBSCRIBE /app/chat.send` — does not match `simpMessageDestMatchers`; proceeds to subsequent rules and is denied if no dedicated subscribe rule exists.
- `SEND /topic/chat/room-42` — does not match the `/app/chat/**` rule; handled by the deny rule for broker destinations.

Authority is an exact string. `hasAuthority("chat:send")` requires a granted authority named `chat:send`. If using `hasRole("USER")`, Spring checks the authority following the `ROLE_USER` convention.

### 5.3. Denying clients from publishing directly to the broker

```java
.simpMessageDestMatchers("/topic/**", "/queue/**")
    .denyAll()
```

This is a critical rule to prevent clients from spoofing messages from the server.

Suppose the system broadcasts maintenance notices over `/topic/system/notifications`. If clients were allowed to `SEND` directly to that destination, a client could broadcast fake notices to all subscribers.

Only allow `SUBSCRIBE` via a separate rule if the user has read permission. Being allowed to `SUBSCRIBE` to a topic does not imply permission to `SEND` to that same topic.

### 5.4. Granting subscribe permission per topic

```java
.simpSubscribeDestMatchers("/topic/chat/**")
    .hasAuthority("chat:read")
```

This rule governs only `SUBSCRIBE` frames. A user with `chat:read` can subscribe to chat topics matching the declared pattern.

If the application has multiple private chat rooms, a broad authority may not be sufficient. For instance, a user with `chat:read` is not necessarily permitted to read `/topic/chat/room-42`. In that case, you need to check the user's membership in the corresponding room using a custom `AuthorizationManager`, path-variable matchers, or appropriate business-level permission checks.

### 5.5. Protecting user destinations

```java
.simpSubscribeDestMatchers("/user/queue/notifications")
    .hasAuthority("notification:read")
```

Clients can subscribe to a user destination such as `/user/queue/notifications`. Spring resolves this destination per the user's Principal/session.

Do not grant broad subscribe permissions to `/queue/**` if the application uses per-session internal queues. Subscribing directly to physical queues can leak messages meant for other users or internal destinations.

### 5.6. Default deny

```java
.simpTypeMatchers(
    SimpMessageType.MESSAGE,
    SimpMessageType.SUBSCRIBE
).denyAll()
.anyMessage().denyAll()
```

The first rule denies send or subscribe operations that lack a specific rule. The final rule denies all remaining messages.

A default-deny policy prevents security gaps when new endpoints are added to the application without updated rules. When opening a new feature, add an explicit rule for the corresponding message type and destination.

## 6. Example from client to controller and broker

Suppose the client has the `chat:send` and `chat:read` authorities.

Client sending data into the application:

```javascript
stompClient.publish({
    destination: "/app/chat.send",
    body: JSON.stringify({
        roomId: "room-42",
        text: "Hello everyone"
    })
});
```

Spring checks the `MESSAGE` frame at `/app/chat.send`. If the user has `chat:send`, the message is routed to the handler:

```java
@Controller
public class ChatController {

    private final SimpMessagingTemplate messagingTemplate;

    public ChatController(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @MessageMapping("/chat.send")
    public void send(ChatRequest request, Principal principal) {
        String sender = principal.getName();

        // Verify the sender has permission to participate in roomId.
        // Persist or process the message per business logic.

        ChatEvent event = new ChatEvent(
                request.roomId(),
                sender,
                request.text()
        );

        messagingTemplate.convertAndSend(
                "/topic/chat/" + request.roomId(),
                event
        );
    }
}

record ChatRequest(String roomId, String text) {}

record ChatEvent(String roomId, String sender, String text) {}
```

Client subscribing to receive data:

```javascript
stompClient.subscribe(
    "/topic/chat/room-42",
    (frame) => {
        const event = JSON.parse(frame.body);
        console.log(event.sender, event.text);
    }
);
```

Spring checks the `SUBSCRIBE` frame at `/topic/chat/room-42`. If the user has `chat:read`, the subscription is accepted. When the server sends an event to the topic, the broker distributes the event to valid subscribers.

If the client attempts to publish directly:

```javascript
stompClient.publish({
    destination: "/topic/chat/room-42",
    body: JSON.stringify({
        sender: "system",
        text: "Fake notification"
    })
});
```

This frame is a `MESSAGE` to `/topic/chat/room-42`, matches the `denyAll()` rule for broker destinations, and is rejected. It does not bypass the controller to impersonate the server.

The controller example only illustrates the processing flow. In a real application, you must validate `Principal`, check room membership, validate the DTO, and handle errors according to system conventions.

## 7. Authentication and authorization are two separate steps

### Authentication

Authentication answers: **Who is connecting?**

Spring WebSocket normally inherits the Principal from the HTTP handshake. If the HTTP request was authenticated by Spring Security, that identity is transferred to the WebSocket session and appears in messages under the `simpUser` header.

For token-based applications, the token must be validated before attaching the Principal to the message/session. Do not treat `login`, `passcode`, or `username` headers in a STOMP frame as a trusted identity if the application does not have a dedicated authentication mechanism for them.

### Authorization

Authorization answers: **What is this user allowed to do?**

`AuthorizationManager<Message<?>>` checks the message type, destination, and user authorities. For example, two users may both be logged in, yet one has `chat:send` while the other only has `chat:read`.

Do not use logged-in status as a reason to automatically permit all `SEND` and `SUBSCRIBE` operations. Permissions must be defined per feature and per data scope the user is allowed to access.

### Business-level permission checks

Destination-based message authorization is still not enough to protect private resources.

For example, a user with `chat:send` can send to `/app/chat.send`, but that does not mean the user is allowed to send to every room. The controller/service must verify whether the user is a member of the room.

```java
@MessageMapping("/chat.send")
public void send(ChatRequest request, Principal principal) {
    String username = principal.getName();

    if (!roomService.isMember(request.roomId(), username)) {
        throw new AccessDeniedException("Not a member of this room");
    }

    // Process the message after room permissions are confirmed.
}
```

Similarly, if a user may only read orders they own, you cannot simply grant an `orders:read` authority and allow subscribing to all order topics. Read access must be bound to each individual order or tenant.

## 8. How does Spring Security protect the inbound channel?

Spring Security registers security interceptors on `clientInboundChannel`, meaning messages traveling from the client into the server. The rules in `AuthorizationManager<Message<?>>` are enforced on this inbound flow.

For data emitted by the server through `clientOutboundChannel`, Spring Security does not run the same authorization mechanism on every outbound message by default. Therefore, **read permissions must be controlled when the client sends `SUBSCRIBE`**. Once a subscription is accepted, the broker can deliver matching messages to the client.

This leads to several requirements:

- Strictly control the destinations clients are allowed to subscribe to.
- Do not let clients subscribe to physical queues or internal destinations.
- When a user's permissions are revoked while the session remains open, consider canceling the subscription/session or applying an appropriate permission-refresh mechanism.
- For private data, verify recipient permissions where the server emits messages.
- Do not rely on an outbound interceptor as the sole security measure.

For instance, if Alice has already subscribed to a chat room topic and is later removed from the room, merely updating permissions in the database may not automatically cancel her active subscription. The application needs a revocation flow for active subscriptions or a destination/session design that handles revocation.

## 9. Testing permissions by message type

When testing, create scenarios for both `MESSAGE` and `SUBSCRIBE`. Do not only test that a user can connect successfully.

| User / Authority | Operation | Destination | Expected result |
|---|---|---|---|
| User with `chat:send` | `MESSAGE` | `/app/chat.send` | Allow |
| User without `chat:send` | `MESSAGE` | `/app/chat.send` | Deny |
| User with `chat:read` | `SUBSCRIBE` | `/topic/chat/room-42` | Allow per sample rules |
| User without `chat:read` | `SUBSCRIBE` | `/topic/chat/room-42` | Deny |
| User with `chat:read` | `MESSAGE` | `/topic/chat/room-42` | Deny |
| User with `chat:send` | `SUBSCRIBE` | `/app/chat.send` | Deny |
| User with `notification:read` | `SUBSCRIBE` | `/user/queue/notifications` | Allow |
| User with `notification:read` | `SUBSCRIBE` | `/queue/notifications` | Deny |
| Logged-in user | `MESSAGE` | `/unknown/action` | Deny by default |
| Unauthenticated user | `CONNECT` | No destination | Deny per sample auth rule |

Tests should assert both allowed and denied outcomes. In particular, verify that read permission does not allow publishing and that permission to send to `/app/**` does not automatically grant permission to read from the broker.

In integration tests, you can use a STOMP client with a corresponding authenticated HTTP session to test the full handshake, CONNECT, SEND, and SUBSCRIBE flow. For unit tests, you can construct a `Message<?>` with Simp headers and invoke `AuthorizationManager` to verify matchers, though this does not completely replace testing the real connection flow.

## 10. Common errors

| Error | Cause | Fix |
|---|---|---|
| Allowing `MESSAGE` and `SUBSCRIBE` with one broad rule | Not separating send and read operations | Use `simpMessageDestMatchers` and `simpSubscribeDestMatchers` |
| Client can send directly to `/topic/**` | Missing rule blocking `MESSAGE` to broker destinations | Deny `MESSAGE` to `/topic/**` and `/queue/**` |
| User can read another person's topic | Subscribe matcher too broad or missing membership check | Grant permissions per destination/resource and verify membership |
| User has `chat:send` but can also subscribe to `/app/**` | Destination matcher does not restrict message type properly | Use separate matchers for `MESSAGE` and `SUBSCRIBE` |
| Only checking HTTP endpoints while forgetting STOMP | Inbound messages are a separate security surface | Enable `@EnableWebSocketSecurity` and configure message authorization |
| Connection rejected at CONNECT | Missing authentication or CSRF token | Check HTTP Principal, CSRF token, and CONNECT headers |
| Adding a new endpoint without a rule | Policy lacks default deny | Use `anyMessage().denyAll()` and add explicit rules |
| User's permission revoked but still receives messages | Subscription was established earlier | Cancel subscription/session or update revocation handling |
| Trusting username/role in STOMP headers | Client can spoof metadata | Use authenticated Principal and server-issued authorities |

## 11. Self-check exercise

An application supports chat rooms with the following authorities:

- `chat:send`: send messages to controllers.
- `chat:read`: read chat topics.
- `notification:read`: read private notifications.

Required policy:

1. Users with `chat:send` may `SEND` to `/app/chat/**`.
2. Users with `chat:read` may `SUBSCRIBE` to `/topic/chat/**`.
3. Users with `notification:read` may `SUBSCRIBE` to `/user/queue/notifications`.
4. All direct `SEND` to `/topic/**` or `/queue/**` are denied.
5. Undeclared destinations and message types are denied.

Answer the following:

1. Why is `simpMessageDestMatchers("/app/chat/**")` appropriate for send permissions?
2. Why is `simpSubscribeDestMatchers("/topic/chat/**")` needed for read permissions?
3. Can a user with both `chat:send` and `chat:read` `SEND` directly to `/topic/chat/room-1`?
4. Why is `anyMessage().denyAll()` useful as the application adds endpoints?
5. If a user is removed from a room after subscribing, what must the application handle?

Answers:

1. This matcher applies only to messages of type `MESSAGE`, i.e., STOMP `SEND` frames.
2. This matcher applies only to messages of type `SUBSCRIBE`, i.e., subscribing to receive data.
3. No. The rule denying `MESSAGE` to broker destinations still blocks that operation; read permission only grants `SUBSCRIBE`.
4. It prevents undeclared messages from being permitted automatically as the application grows.
5. The subscription/session must be revoked, or a mechanism must ensure the user stops receiving data once access is lost.

## 12. Key takeaways

- `SEND` maps to `SimpMessageType.MESSAGE`; `SUBSCRIBE` maps to `SimpMessageType.SUBSCRIBE`.
- `/app/**` is for commands sent to controllers; `/topic/**` and `/queue/**` are typically for the broker.
- Use `simpMessageDestMatchers` to control send permissions and `simpSubscribeDestMatchers` to control read permissions.
- Block direct `MESSAGE` frames to broker destinations so clients cannot spoof server messages.
- Only allow `SUBSCRIBE` to destinations the user is authorized to read.
- `@EnableWebSocketSecurity` protects the inbound channel and requires a CSRF token for CONNECT by default.
- Spring Security controls inbound subscriptions; it does not authorize individual outbound messages by default.
- Destination authorization must be paired with membership, ownership, and business permission checks.
- Use default deny so new endpoints do not accidentally open up access.

## References

- Spring Security Reference — [WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- Spring Security API — [MessageMatcherDelegatingAuthorizationManager.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html)
- Spring Framework Reference — [STOMP Authorization](https://docs.spring.io/spring/reference/web/websocket/stomp/authorization.html)
- Spring Framework Reference — [Flow of Messages](https://docs.spring.io/spring/reference/web/websocket/stomp/message-flow.html)
- Spring Security API — [EnableWebSocketSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/socket/EnableWebSocketSecurity.html)
