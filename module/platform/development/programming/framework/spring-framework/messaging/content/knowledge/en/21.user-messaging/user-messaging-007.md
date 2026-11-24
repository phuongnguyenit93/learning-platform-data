# Broadcasting and Targeting One or Multiple Sessions of the Same User

> Scope: Spring Framework STOMP over WebSocket, Java 17+. This lesson focuses on user destinations, how Spring sends messages to multiple WebSocket sessions of the same user, and how to restrict replies to the session that sent the request. The Java snippets are integration code within a Spring application with STOMP configured, not standalone programs.

## 1. What does "send to user" mean?

In a WebSocket application, a single user can open multiple concurrent connections: multiple browser tabs, multiple windows, a desktop computer, and a phone. Each WebSocket/STOMP connection has its own session, yet authenticated sessions can all represent the same account.

Spring supports **user destinations** to send messages to the sessions associated with a user. The client subscribes to a logical destination, for example:

~~~javascript
stompClient.subscribe("/user/queue/notifications", frame => {
    const notification = JSON.parse(frame.body);
    console.log(notification);
});
~~~

The client does not need to know the username or the physical destination of each session. When sending a message, the server specifies the user and the target destination. Spring resolves the user destination into one or more destinations specific to connected sessions.

Key point: "broadcast to a user" means sending to the sessions of **one specific user**. It does not mean broadcasting to every connected user like a public topic.

## 2. Configuring user destinations

A STOMP configuration typically has an application prefix for messages sent into controllers, broker prefixes for distributed messages, and a user destination prefix:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

`/user` is Spring's default prefix for user destinations; declaring it explicitly makes the configuration easier to read. `/app` routes inbound messages to `@MessageMapping`. `/topic` and `/queue` are prefixes handled by the broker.

A client subscribes to `/user/queue/notifications`. When the server sends to user `alice` with destination `/queue/notifications`, Spring processes the user destination and routes the message to the actual destinations of sessions belonging to `alice`. Internal destinations may include a session identifier; the client does not need to construct or guess those names.

Overview flow:

~~~text
Client SUBSCRIBE /user/queue/notifications
                 |
                 v
        User destination handler
                 |
          session A, session B

Server sends to user "alice"
                 |
                 v
 /user/alice/queue/notifications
                 |
          User destination resolver
                 |
       +---------+---------+
       |                   |
  destination A       destination B
       |                   |
    session A           session B
~~~

The diagram above illustrates sending to all sessions of the user. When restricted to the originating session, Spring only creates a target for the session that sent the inbound message.

## 3. @SendToUser: sending results to a user's sessions

`@SendToUser` is used on a message-handling method to send the return value to the user associated with the inbound message. The exact import is:

~~~java
import org.springframework.messaging.simp.annotation.SendToUser;
~~~

For example, suppose the user is logged in and Spring can determine the connection's `Principal`:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class PrivateReplyController {

    public record PingRequest(String text) {}
    public record PrivateReply(String username, String text) {}

    @MessageMapping("/account/ping")
    @SendToUser("/queue/replies")
    public PrivateReply reply(PingRequest request, Principal principal) {
        return new PrivateReply(
            principal.getName(),
            "Server received: " + request.text()
        );
    }
}
~~~

The client sends to `/app/account/ping`. Spring strips the `/app` application prefix to locate `@MessageMapping("/account/ping")`. The return value is converted into a message payload and sent to the user destination `/queue/replies`.

The client subscribes to `/user/queue/replies` to receive the reply. Do not include the username in the subscribe destination and do not write `/user/{username}` in the `@SendToUser` value; Spring handles that part.

### Default behavior: broadcast = true

The `broadcast` attribute of `@SendToUser` defaults to `true`. Therefore, when an authenticated user has multiple connected sessions, the message is sent to all sessions of that user subscribed to the corresponding destination.

For example, the same `alice` account is open on:

- Tab A on a computer and subscribed to `/user/queue/replies`.
- Tab B on the same computer and subscribed to `/user/queue/replies`.
- A mobile app and subscribed to `/user/queue/replies`.

When one of `alice`'s sessions sends `/app/account/ping`, all three sessions with matching subscriptions can receive the reply message. The "already subscribed" condition is crucial: Spring does not auto-create subscriptions for clients, and the broker does not replay old messages to a session that subscribes later.

This is a broadcast scoped to a single user. Other accounts, such as `bob`, do not receive the message merely because they are also subscribed to `/user/queue/replies`; Spring resolves destinations by user identity.

### Sending only to the requesting session: broadcast = false

If the reply is intended only for the tab or device that just sent the message, set `broadcast = false`:

~~~java
@MessageMapping("/account/ping-current-session")
@SendToUser(value = "/queue/replies", broadcast = false)
public PrivateReply replyOnlyToOriginatingSession(
        PingRequest request,
        Principal principal) {

    return new PrivateReply(
        principal.getName(),
        "Reply for the session that sent this request"
    );
}
~~~

Suppose Tab A and Tab B are both logged in with the `alice` account. If Tab A sends a message to `/app/account/ping-current-session`, only Tab A's session receives the reply. Tab B may still be subscribed to the same `/user/queue/replies`, yet it does not receive the message from this invocation.

`broadcast = false` means **only the session that sent the inbound message being processed**. It is not a parameter for arbitrarily selecting another session by session ID. If a service needs to proactively target an arbitrary session, the application must design its own session routing mechanism and manage session lifecycles appropriately.

When a user has only one session, `broadcast = true` and `broadcast = false` typically produce the same observable result. The difference only becomes apparent when the same user has multiple sessions.

## 4. Comparison of sending approaches

| Sending approach | Recipient scope | When to use |
|---|---|---|
| `@SendTo("/topic/events")` | All authorized subscribers on the topic | Broadcasting shared events to many users. |
| `@SendToUser("/queue/replies")` | All matching sessions of the sending user; default `broadcast = true` | Syncing replies or state across devices of the same user. |
| `@SendToUser(value = "/queue/replies", broadcast = false)` | Only the session that sent the inbound message | Private reply for the active tab or device performing the action. |
| `SimpMessagingTemplate.convertAndSendToUser(...)` | Sessions of the specified username | Proactive sending from a service or background task to a user. |

Do not use `/topic` just because you want to send to multiple tabs of the same user. `/topic` distributes to subscriptions on a shared destination; user destinations distribute by user identity and that user's sessions.

## 5. Proactive sending with SimpMessagingTemplate

Not every message is sent from the return value of `@MessageMapping`. A service may need to emit notifications after business processing, after persisting data, or when a background job completes. In those cases, use `SimpMessagingTemplate`:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserNotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public UserNotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String username, Notification notification) {
        messagingTemplate.convertAndSendToUser(
            username,
            "/queue/notifications",
            notification
        );
    }

    public record Notification(String title, String message) {}
}
~~~

`convertAndSendToUser(username, destination, payload)` accepts the user name, user-relative destination, and payload. Under normal user destination configuration, the message is resolved to active sessions of that username subscribed to the corresponding destination.

For example, if `username` is `alice`, Alice's client still subscribes to `/user/queue/notifications`. The service does not send directly to `/user/alice/queue/notifications`; the template constructs the user destination for Spring to process.

`convertAndSendToUser` is useful for proactive sending and by default targets all sessions of the user. It does not have a `broadcast=false` parameter like the annotation. If you need to restrict a reply to the session that sent an inbound message, `@SendToUser(..., broadcast = false)` is the direct declarative way inside a handler. If you need to target a specific session from a service, build a dedicated session-aware strategy instead of manually assembling the internal destination names generated by Spring.

The user name passed to the template must match the identity that the application attaches to `Principal`. Do not take a target username from an arbitrary client-supplied payload field and use it to route private notifications; determine the recipient from the authenticated context and server-side business rules.

## 6. Unauthenticated session cases

For authenticated connections, Spring uses `Principal` to group multiple sessions belonging to the same user. For an anonymous session without a `Principal`, `@SendToUser` can still send a reply, but Spring treats the current session as the target and only sends back to the session that sent the message. There is no shared user identity to broadcast to other tabs or devices.

Therefore, if the application expects to synchronize multiple devices of the same account, ensure that WebSocket/STOMP authentication attaches the same `Principal` identity to that account's connections. If each connection lacks a Principal or receives different identities, Spring cannot automatically infer that they belong to the same user.

It is also important to distinguish a user from a session:

- **User** is an application identity, typically represented by `Principal.getName()`.
- **Session** is a specific WebSocket/STOMP connection.
- A logged-in user can own multiple sessions.
- An unauthenticated session can still receive session-private replies via the user destination mechanism, but there is no account-wide broadcast.

## 7. Complete example of both options

The following controller provides two endpoints: one sends to all sessions of the user, and one sends only to the originating session.

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class SessionReplyController {

    public record Request(String action) {}
    public record Reply(String user, String message) {}

    // Default broadcast = true: sends to all sessions of the user.
    @MessageMapping("/session/all")
    @SendToUser("/queue/session-replies")
    public Reply replyToAllSessions(Request request, Principal principal) {
        return new Reply(
            principal.getName(),
            "Action processed: " + request.action()
        );
    }

    // broadcast = false: sends only to the session that sent this message.
    @MessageMapping("/session/current")
    @SendToUser(value = "/queue/session-replies", broadcast = false)
    public Reply replyToCurrentSession(Request request, Principal principal) {
        return new Reply(
            principal.getName(),
            "Action processed in the originating session: " + request.action()
        );
    }
}
~~~

The client in each tab or device subscribes to the same logical destination:

~~~javascript
stompClient.subscribe("/user/queue/session-replies", frame => {
    const reply = JSON.parse(frame.body);
    console.log(reply.message);
});
~~~

Tab A sends to `/app/session/all`: all subscribed sessions of the same user receive the same result. Tab A sends to `/app/session/current`: only Tab A receives the result of that invocation.

Both endpoints return the same DTO type and use the same subscription destination. Deciding how many sessions receive the message lies in `broadcast`, not in the payload structure.

## 8. Common errors and handling

| Symptom | Common cause | How to handle |
|---|---|---|
| No session receives the message | Client subscribed to `/queue/...` instead of `/user/queue/...` | Subscribe to the logical destination starting with `/user`. |
| Only the requesting tab receives it | `broadcast = false` or connection has no Principal | Check the `broadcast` value and STOMP authentication. |
| All devices of the same account receive the reply unexpectedly | `broadcast` defaults to `true` | Set `broadcast = false` if only the originating session is needed. |
| Other users also receive the message | Sending to a shared topic instead of a user destination | Use `@SendToUser` or `convertAndSendToUser`. |
| Multiple connections of one account are treated as different users | Inconsistent Principal across connections | Check authentication flow and `Principal.getName()` values. |
| `convertAndSendToUser` routes to nobody | Username does not match identity in user registry or no matching session exists | Use the exact username from the authenticated context; verify sessions and subscriptions. |
| Service wants to send to one specific tab but all tabs receive it | Using `convertAndSendToUser`, which sends by user | Design separate session routing; do not confuse it with `broadcast = false` in a handler. |
| Client connecting later misses prior notifications | Broker does not store messages for replay | Persist required state/events in the application and provide a sync API when the client connects. |

When debugging, check in order:

1. Is the STOMP connection authenticated and what is `Principal.getName()`?
2. Do the tabs/devices actually share the same user identity?
3. Did the client subscribe to `/user/queue/...` before the message was sent?
4. Does the handler use `@SendToUser` with the right destination?
5. Is `broadcast` set to `true` or `false`?
6. If sending from a service, does the username in `convertAndSendToUser` match the user registry?

## 9. Quick selection rules

- Want all subscribers of a topic to receive the message: use `@SendTo`.
- Want all sessions of an account to receive the reply: use `@SendToUser` with the default `broadcast = true`.
- Want only the tab/device that just sent the request to receive the reply: use `@SendToUser(..., broadcast = false)`.
- Want a service to send a notification to an account: use `SimpMessagingTemplate.convertAndSendToUser`.
- Want to target an arbitrary session from a background task: design custom session routing; `broadcast = false` only identifies the originating session of the message currently being processed.

## 10. Self-check

1. A user logs in on a laptop and a phone. Both sessions subscribe to `/user/queue/alerts`. The handler uses `@SendToUser("/queue/alerts")`. How many sessions can receive the message?
2. Same scenario, the handler uses `@SendToUser(value = "/queue/alerts", broadcast = false)` and the laptop sends the request. Which session receives the reply?
3. Does `broadcast = false` allow the server to pick an arbitrary session by ID?
4. Should the client subscribe to `/user/queue/alerts` or `/user/alice/queue/alerts`?
5. A session without a Principal sends a message to a handler with `@SendToUser`. Where can Spring send the reply?

Answers:

1. Both the laptop and the phone, if both sessions are active and subscribed to that destination.
2. Only the laptop session that sent the request.
3. No. It restricts the reply to the originating session of the inbound message.
4. `/user/queue/alerts`; Spring resolves the username and sessions itself.
5. Back to the anonymous session that sent the message; there is no account-based broadcast.

## References

- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): user destinations, `@SendToUser`, broadcasting to multiple sessions, and anonymous sessions.
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): handling return values and annotations for sending messages from controllers.
- [Spring Framework — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html): proactive message sending via `SimpMessagingTemplate`.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): message flow across Spring STOMP channels.
