# convertAndSendToUser with Principal Name

## Learning Objectives

After this lesson, you can:

- Explain how Spring sends messages to a specific user via user destinations.
- Obtain the exact identifier from `java.security.Principal#getName()` as the routing key.
- Distinguish the destination subscribed to by the client from the destination passed by the server to `convertAndSendToUser`.
- Configure the broker and inject `SimpMessagingTemplate` into a service or controller.
- Understand how Spring locates active sessions of a user and handle the case where no session exists.
- Avoid using client-declared usernames or headers as the basis for authentication and authorization.

## 1. The problem of sending a message to a single user

In WebSocket/STOMP applications, `/topic` is typically used for messages broadcast to multiple subscribers, while `/queue` is typically used for private-stream messages. However, simply choosing a destination like `/queue/notifications` is not enough for Spring to know whose connection session to send to.

Spring Messaging provides **user destinations** to route messages by the user attached to the WebSocket session. The application can send a private notification to a user whose Principal name is `alice` without manually creating physical destinations for each session.

Both sides use two different destination forms:

- The client subscribes to receive messages at `/user/queue/notifications`.
- The server calls `convertAndSendToUser("alice", "/queue/notifications", payload)`.

The `/user` prefix tells the client this is a user destination. During processing, Spring resolves the user destination into internal destinations bound to one or more active sessions of that user. Therefore, the server passes the destination portion after the user prefix, such as `/queue/notifications`.

This is a routing mechanism at the messaging layer. It does not authenticate users on its own, does not store messages into an offline mailbox, and does not replace the application's authorization rules.

## 2. `Principal` and the identifier used for routing

`java.security.Principal` represents the identity of the authenticated entity in a connection. The most important method is:

```java
String getName();
```

In Spring WebSocket/STOMP, a Principal is typically associated with the WebSocket session through the application's authentication process, such as HTTP handshake authentication or Spring Security integration. Spring uses the Principal attached to the session to identify the user when handling user destinations.

When sending a message, the first parameter of `convertAndSendToUser` is the **user name as a String**. Therefore, obtain the name with `principal.getName()`:

```java
Principal principal = ...;

String username = principal.getName();
messagingTemplate.convertAndSendToUser(
        username,
        "/queue/notifications",
        notification
);
```

Do not pass the Principal object directly into the user parameter. Do not use `principal.toString()`, a display name, a guessed email, or an arbitrary header sent by the client. The value to use is the identifier that the authentication system attached to the Principal.

The name must match the user registered in Spring's user registry of active WebSocket sessions. For example, if the user's session is registered with `Principal#getName() = "alice"`, then calling send to `"alice"` will route to the corresponding sessions.

### Principal may be absent

A handler that only permits authenticated users should be protected by the application's security configuration. Even so, when writing code, you should still handle the case where Principal is absent or its name is blank, especially if the handler can also be reached from flows that do not require login.

```java
private String requireUsername(Principal principal) {
    if (principal == null || principal.getName() == null
            || principal.getName().isBlank()) {
        throw new IllegalStateException(
                "An authenticated Principal is required"
        );
    }
    return principal.getName();
}
```

In a real application, use exceptions and responses consistent with the project's security conventions. Never turn an absent Principal into a default user or use a client-sent name as a substitute.

## 3. `SimpMessagingTemplate.convertAndSendToUser`

`org.springframework.messaging.simp.SimpMessagingTemplate` is the abstraction for sending messages through Spring's message channels. It supports sending messages to regular destinations and to user destinations.

Basic call:

```java
messagingTemplate.convertAndSendToUser(
        username,
        "/queue/notifications",
        payload
);
```

Meaning of the three arguments:

| Argument | Meaning |
|---|---|
| `user` | Recipient identifier, usually `Principal#getName()` |
| `destination` | Application-side destination, e.g., `/queue/notifications` |
| `payload` | Data object to be converted into a message by the message converter |

The `convertAndSendToUser` method converts the payload into a message and sends it to the user destination. The template class also has overloads accepting a headers map and a message post-processor when the application needs to add metadata or process the message before sending. Only add headers when there is a clear need; do not use client-supplied headers as the basis for authentication.

Example of a notification-sending service:

```java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(
            SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(
            String username,
            Notification notification) {

        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                notification
        );
    }
}

public record Notification(String title, String message) {}
```

The service receives a username already determined from a trusted source. It does not infer the recipient from arbitrary data in the payload.

## 4. Client and server destinations

This is the easiest part to confuse when first using user destinations.

Suppose the broker is configured to handle `/queue` and `/topic` destinations, and the user destination prefix is `/user`.

Alice's client subscribes:

```javascript
stompClient.subscribe(
    "/user/queue/notifications",
    (frame) => {
        const notification = JSON.parse(frame.body);
        console.log(notification.title, notification.message);
    }
);
```

Server sends:

```java
messagingTemplate.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        new Notification(
                "Order confirmed",
                "Order ORD-100 has been received."
        )
);
```

Spring combines the user name with the user destination prefix to create an internal user destination, then resolves that destination to Alice's sessions. The client does not need to know the physical destination specific to its session.

**Do not add `/user` to the destination argument of `convertAndSendToUser`.** In the default configuration, pass `/queue/notifications` on the server side and let the client subscribe to `/user/queue/notifications`. If you mistakenly pass `/user/queue/notifications` as the destination argument, you are putting the user prefix into the destination portion already handled by the template, resulting in an incorrect path.

If the application changes the prefix via `setUserDestinationPrefix`, both the destination the client subscribes to and the application's routing must follow the new prefix. Do not assume every application uses `/user` if the configuration has been changed.

## 5. Configuring the message broker

A minimal STOMP configuration typically declares the WebSocket endpoint, application destination prefixes, and broker destination prefixes:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

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
        // Default user destination prefix is "/user".
    }
}
```

Meaning:

- Clients send inbound messages to destinations prefixed with `/app`; Spring routes them to `@MessageMapping`.
- The broker handles destinations prefixed with `/topic` or `/queue` as configured.
- User destinations default to the `/user` prefix and are resolved by Spring before the message reaches the broker.
- `SimpMessagingTemplate` is provided in the message broker infrastructure enabled by `@EnableWebSocketMessageBroker` and can be injected into Spring beans.

If the application uses a broker relay instead of the simple broker, appropriate destination prefixes still need to be configured and the broker relay must receive the destination after Spring resolves the user destination.

## 6. Obtaining Principal in `@MessageMapping` and sending to that same user

Spring can resolve the current session's `Principal` as a handler parameter. The following example sends a private reply notification to the user sending the request:

```java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
public class NotificationController {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationController(
            SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @MessageMapping("/notifications.request")
    public void requestNotification(
            @Payload NotificationRequest request,
            Principal principal) {

        String username = requireUsername(principal);

        Notification response = new Notification(
                "Request received",
                "Request " + request.reference() + " has been received."
        );

        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                response
        );
    }

    private String requireUsername(Principal principal) {
        if (principal == null || principal.getName() == null
                || principal.getName().isBlank()) {
            throw new IllegalStateException(
                    "An authenticated Principal is required"
            );
        }
        return principal.getName();
    }
}

record NotificationRequest(String reference) {}

record Notification(String title, String message) {}
```

The client sends a request to `/app/notifications.request` and has subscribed to `/user/queue/notifications`. When the handler runs, Spring supplies the Principal of the current session. The controller extracts the Principal name and sends the response to the corresponding user destination.

This is an integrated example within a Spring application already configured with WebSocket/STOMP, a message broker, and authentication. The records are placed alongside the example to illustrate DTO structure; the snippet is not a standalone program runnable solely with `javac`.

## 7. Sending to a different user

Many business flows need to send to a recipient different from the person making the request, such as notifying an assigned staff member when an order is created.

In that case, the service receives the target user name from a trusted source, typically looked up from business data:

```java
public void notifyAssignee(
        Order order,
        String assigneeUsername) {

    Notification notification = new Notification(
            "New order",
            "You have been assigned to handle " + order.getNumber()
    );

    messagingTemplate.convertAndSendToUser(
            assigneeUsername,
            "/queue/notifications",
            notification
    );
}
```

In this example, `assigneeUsername` must come from a server-verified assignment result. Do not accept a username from the payload and send arbitrarily without verifying that the sender has permission to perform that action.

Two values must be distinguished:

- **Sender's Principal**: the authenticated identity of the session performing the request.
- **Recipient's Username**: the user to whom the business logic wants to send the message.

These two values may be the same or different. `convertAndSendToUser` only routes according to the user name passed in; it does not decide whether the sender is authorized to send to the recipient.

## 8. How does Spring handle user destinations?

Overview flow:

1. The client connects over WebSocket and is bound to an authenticated Principal.
2. Spring registers the session along with the user name in the user registry.
3. The client subscribes to `/user/queue/notifications`.
4. The server calls `convertAndSendToUser("alice", "/queue/notifications", payload)`.
5. Spring creates a message sent to the user destination containing Alice's name.
6. `UserDestinationMessageHandler` and the user destination resolution mechanism locate the corresponding sessions.
7. Spring forwards the message to internal destinations bound to matching sessions.
8. The broker delivers the message to clients that subscribed to receive it.

User destinations allow multiple sessions to share the same Principal name. By default behavior, a message sent to a user can be resolved to all active sessions of that user. For example, if Alice opens the application in two tabs logged into the same account, both sessions can receive the notification.

If business logic requires sending to only one specific session, you must explicitly design the session selection mechanism and corresponding session metadata. Sending to a user should not be confused with sending solely to a single tab or a single device.

The user registry tracks active sessions. If a user has no matching session, the message does not automatically become a mailbox record for the user to read upon logging back in. For notifications that require durable storage, write events/notifications to a database or durable queue, then use WebSocket to notify the client that new data is available.

### Applications running on multiple nodes

In a multi-instance deployment, each node may only know about sessions connected to that node. If cross-node user destination routing is required, you must configure user registry sharing/broadcasting and unresolved destination broadcasting according to Spring's supported model. Specific configuration depends on the broker architecture and application topology; do not assume a local simple broker automatically syncs sessions between nodes.

## 9. Distinguishing from `@SendToUser`

Spring also provides the `@SendToUser` annotation to send a handler's return value to a user destination. Example:

```java
@MessageMapping("/profile.refresh")
@SendToUser("/queue/profile")
public ProfileView refreshProfile(Principal principal) {
    return profileService.load(principal.getName());
}
```

The two approaches have similar goals but different usage patterns:

| Approach | Best suited when |
|---|---|
| `@SendToUser` | Routing the return value of a handler to the current user |
| `convertAndSendToUser` | Proactively sending a message from a controller, service, or business component to a specified user |

`convertAndSendToUser` is useful when the event originates outside the lifecycle of a STOMP handler, such as after a service processes an order, a background task finishes, or a result arrives from another system.

With `@SendToUser`, the `broadcast` attribute defaults to `true`. You can set `broadcast = false` if you only want to send to the session processing the inbound message. That rule belongs to the annotation; do not assume every template call shares the same annotation configuration.

## 10. Security when routing by Principal

User destinations rely on the Principal attached to the session, but the template call itself is not an authorization mechanism.

Principles to apply:

- **Authenticate before attaching identity.** The Principal must come from the application's trusted authentication mechanism, typically HTTP handshake/Spring Security.
- **Do not trust identity headers sent by the client.** Headers such as `user`, `username`, `x-user-id`, or `role` can be spoofed. Never use them in place of `Principal#getName()`.
- **Check authorization when sending to another user.** A user may only send to recipients permitted by business logic, such as a server-determined assignee.
- **Protect inbound destinations.** Use Spring Security message authorization to restrict who can send to `/app/**` and who can subscribe to appropriate destinations.
- **Do not let clients subscribe to internal destinations.** Clients should subscribe to public user destinations like `/user/queue/notifications`; do not arbitrarily grant permissions to resolved physical destinations.
- **Use consistent Principal names.** The authentication provider, user registry, and template calls must follow the same naming convention, including case normalization if defined by the system.
- **Do not put secrets in payloads or logs.** Notifications should contain minimal data; avoid logging tokens, session secrets, or sensitive personal information.

In particular, knowing a username does not mean the caller has permission to send messages to that user. Permission checks must take place at the business or security layer before calling the template.

## 11. Common errors and fixes

| Symptom | Common cause | How to check/fix |
|---|---|---|
| Client subscribes properly but receives no message | User argument does not match session's Principal name | Controlled-log `Principal#getName()` during handshake/handler and compare with the name passed to the template |
| Client receives nothing due to wrong destination | Server passes `/user/queue/...` instead of the `/queue/...` destination portion | Use `/user/queue/...` on client and `/queue/...` on server |
| Principal is null when accessed | Session is unauthenticated or Principal was not attached to WebSocket session | Check handshake, authentication configuration, and anonymous access policy |
| Message sent to the wrong person | Using a username from client-controlled payload/headers | Obtain identity from Principal or look up recipient via server-side business logic |
| Only some tabs receive the message | Sessions do not share the same Principal name or a session is no longer active | Check user registry and the identity attached to each session |
| Messages lost when user is offline | User destination is not a durable queue | Persist notifications to a database/durable queue and emit events when the user is online |
| Multi-node setup fails to deliver to user on another node | User registry is not shared or broadcast properly | Configure user registry broadcast and unresolved destination broadcast according to the architecture |
| No template bean available to inject | Message broker is not enabled/configured in context | Check `@EnableWebSocketMessageBroker` and WebSocket configuration |

When debugging, check in order: the session's Principal, the username passed in, the server destination, the client subscribe destination, broker prefixes, and connection state. Do not log entire frames if frames may contain sensitive information.

## 12. Self-check exercise

An application has two logged-in users, Alice and Bob. Each subscribes to receive notifications at `/user/queue/notifications`. After Bob is assigned to handle an order, the server needs to send a private notification to Bob.

Answer the following:

1. What value should be passed to the `user` argument of `convertAndSendToUser`?
2. What destination is passed to the template?
3. What destination does Bob's client subscribe to?
4. Can Bob's username be taken from an `x-user-name` header sent by Alice's client?
5. If Bob is logged in across two tabs with the same Principal name, what can happen?

An appropriate call after the server determines the assignee:

```java
messagingTemplate.convertAndSendToUser(
        bobUsername,
        "/queue/notifications",
        new Notification(
                "New order",
                "You have been assigned to handle ORD-100."
        )
);
```

Answers:

1. Bob's identifier in the user registry, usually `Principal#getName()` of Bob's session or the username looked up by the server from a trusted source.
2. `/queue/notifications`.
3. `/user/queue/notifications`.
4. No. Alice could set that header herself; the server must use the authenticated Principal or server-side assignment data.
5. Both of Bob's sessions can receive the message under the default user destination resolution behavior.

## 13. Key takeaways

- `Principal#getName()` provides the identifier for Spring to route to a user's sessions.
- `convertAndSendToUser(userName, destination, payload)` sends the converted payload to the user destination.
- Clients subscribe to `/user/queue/notifications`; the server passes `/queue/notifications` to the template.
- User destinations are resolved by Spring into internal destinations for the user's active sessions.
- User destinations are not an offline mailbox and do not perform authorization on their own.
- Use the authenticated Principal; verify business permissions before sending to another user.
- Use a separate persistence mechanism if notifications must be retained while the recipient is offline.

## References

- Spring Framework Reference — [User Destinations](https://docs.spring.io/spring/reference/web/websocket/stomp/user-destination.html)
- Spring Framework Reference — [STOMP Message Flow](https://docs.spring.io/spring/reference/web/websocket/stomp/message-flow.html)
- Spring Framework Javadoc — [SimpMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/SimpMessagingTemplate.html)
- Spring Framework Javadoc — [UserDestinationMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/UserDestinationMessageHandler.html)
- Spring Framework Javadoc — [Principal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Principal.html)
