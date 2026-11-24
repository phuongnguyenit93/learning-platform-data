# Experimenting with User-Specific Notifications Across Multiple Sessions

A user can be logged in from multiple places simultaneously: two browser tabs, a laptop and a phone, or multiple application windows. Each WebSocket/STOMP connection creates its own session, yet those sessions may be associated with the same authenticated Principal. When the server sends a notification to a user, Spring must determine whether to send it to all of that user's sessions or only to the session performing a particular action.

Spring STOMP supports user destinations via the `/user/` prefix. This mechanism lets a client subscribe to a generic destination like `/user/queue/notifications`; Spring resolves it into a session-specific destination. On the server side, you can send to a user using `SimpMessagingTemplate.convertAndSendToUser(...)` or `@SendToUser`.

The experiment below creates two connections for the same user `alice`, plus one connection for `bob` to verify isolation. The test confirms three behaviors: a service notification sent to Alice reaches both subscribed sessions; `@SendToUser` broadcasts to Alice's sessions by default; `broadcast=false` replies only to the session that originated the request.

## 1. Multi-Session Model for a Single User

Distinguish three identifiers:

- **Principal / username:** authenticated identity of the user, e.g., `alice`.
- **WebSocket session ID:** identifier of each WebSocket connection. Each tab or device normally has a different session ID.
- **STOMP subscription ID:** subscription identifier within a STOMP session. One session can subscribe to multiple destinations.

Example of Alice logged in on both a browser and a phone:

~~~text
Principal: alice
  |
  +-- WebSocket session: ws-101
  |     +-- STOMP subscription: /user/queue/notifications
  |     +-- STOMP subscription: /user/queue/orders
  |
  +-- WebSocket session: ws-202
        +-- STOMP subscription: /user/queue/notifications

Principal: bob
  |
  +-- WebSocket session: ws-303
        +-- STOMP subscription: /user/queue/notifications
~~~

Both `ws-101` and `ws-202` share Principal `alice`, yet they are two independent connections. Session `ws-303` belongs to `bob`, so it must not receive Alice's private notifications.

### 1.1. How Spring Resolves User Destinations

The client subscribes to the logical destination:

~~~text
/user/queue/notifications
~~~

`UserDestinationMessageHandler` intercepts destinations prefixed with `/user/` and resolves them into per-session physical destinations, for example:

~~~text
Alice / ws-101 -> /queue/notifications-user101
Alice / ws-202 -> /queue/notifications-user202
Bob   / ws-303 -> /queue/notifications-user303
~~~

The suffixes above are illustrative only; do not depend on how Spring constructs internal names. The key point is that each session's subscription is isolated. Multiple users subscribing to `/user/queue/notifications` do not receive each other's messages.

When the server sends to user `alice`, Spring looks up Alice's active registered sessions and forwards the message to the corresponding destinations. Only sessions that subscribed to the target destination receive the message. A connected session that has not subscribed to `/user/queue/notifications` will not automatically receive that notification.

### 1.2. User Destinations Are Not an Offline Mailbox

User destinations route to active, subscribed sessions. If Alice has no remaining sessions, notifications are not automatically stored in a mailbox for delivery when she logs back in.

If business logic requires offline notifications, persist notifications in a database or durable message store, then synchronize when the client connects. WebSocket push should be viewed as a real-time update channel; read state, history, and redelivery must be managed at the business layer.

## 2. Configuring STOMP Endpoints and the Broker

Spring WebSocket needs two destination groups:

- `/app`: messages sent by clients to the application to be handled by `@MessageMapping`.
- `/queue` or `/topic`: broker-managed destinations for sending to subscribers.

Simple configuration example using the built-in simple broker:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/queue", "/topic");
    }
}
~~~

Clients open a WebSocket connection to `/ws`, then send STOMP frames. Messages whose destination starts with `/app` are routed to controllers; messages starting with `/queue` or `/topic` are forwarded to the broker.

The simple broker is suitable for experiments and simple applications. It stores subscriptions in process memory, is not a distributed broker, and does not provide durability like a dedicated broker. When deploying multiple application nodes or when full broker features are needed, use a STOMP broker relay to a STOMP-capable broker.

### 2.1. Prefixes Must Be Configured Correctly

User destinations are handled by `UserDestinationMessageHandler`. If the broker receives `/user/**` destinations directly, the broker may mishandle messages that Spring has not resolved yet. Ensure `/user` is not configured as a regular broker prefix.

Clients subscribe to `/user/queue/notifications`; when sending from a service, pass the username and the logical destination `/queue/notifications` to `convertAndSendToUser`. Do not manually prepend `/user/{username}` to the second destination argument.

## 3. Sending Notifications to All Sessions of a User

From any service, you can inject `SimpMessagingTemplate`:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String username, String message) {
        this.messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                message);
    }
}
~~~

When calling:

~~~java
notificationService.notifyUser("alice", "Order has been delivered");
~~~

Spring finds `alice`'s current sessions and sends to those with a `/user/queue/notifications` subscription. If Alice has both a browser and a phone open, both receive the notification. Bob's session does not receive it.

`convertAndSendToUser` is suitable for notifications triggered by services, scheduled jobs, event listeners, or business processing results. The caller does not need to know each tab's session ID.

### 3.1. Do Not Send Using a Client-Declared Username

The username passed to `convertAndSendToUser` must come from authenticated state or server-side business data. Do not take an arbitrary username from a client payload and use it as the target recipient.

A client must not claim to be Alice by sending a STOMP header `login: alice` or sending a message to another user's destination. In WebSocket applications, Spring uses the Principal bound to the HTTP handshake; login details in STOMP CONNECT do not replace server-side authentication.

## 4. @SendToUser: Default Broadcast vs. broadcast=false

`@SendToUser` sends the return value of a `@MessageMapping` method to the user associated with the input message.

### 4.1. Default: Send to All User Sessions

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
class NotificationController {

    @MessageMapping("/notify-all")
    @SendToUser("/queue/notifications")
    public String notifyAllSessions(String message) {
        return message;
    }
}
~~~

Alice's client sends to `/app/notify-all`. The return value is sent to all of Alice's sessions subscribed to `/user/queue/notifications`. By default, `broadcast` on `@SendToUser` is `true`, so multiple sessions belonging to the same user can all receive the result.

This behavior fits when an action on one device needs to update other devices, such as order status, profile changes, account balance, or login alerts.

### 4.2. Reply Only to the Originating Session: broadcast=false

Sometimes a message is meant only for the tab that sent the request, for example:
- Validation errors for an open form.
- Errors for a specific operation.
- Temporary feedback for a UI control command.
- Autocomplete results or queries serving only the current screen.

You can use:

~~~java
@MessageMapping("/notify-current")
@SendToUser(
        destinations = "/queue/notifications",
        broadcast = false)
public String notifyCurrentSession(String message) {
    return message;
}
~~~

If Alice sends `/app/notify-current` from session `ws-101`, only the session that sent that message receives the result. Alice's `ws-202` session and Bob's session do not receive it.

`broadcast=false` is especially useful for `@MessageExceptionHandler`: an error from a message is returned strictly to the client session that caused it, preventing another tab from receiving an unrelated error alert.

~~~java
@MessageMapping("/update-profile")
public void updateProfile(ProfileCommand command) {
    // Validate and update profile.
}

@MessageExceptionHandler
@SendToUser(
        destinations = "/queue/errors",
        broadcast = false)
public ApplicationError handleProfileError(ProfileValidationException ex) {
    return new ApplicationError("INVALID_PROFILE", ex.getMessage());
}
~~~

`broadcast=false` relies on the session of the message currently being handled. A background job has no originating request session; therefore, do not use it as a device-selection mechanism from a background service. If business logic needs to target a specific device, design explicit device/session identifiers and routing at the application layer.

### 4.3. Sessions Without a Principal

Spring still allows a WebSocket session not yet bound to an authenticated user to subscribe to user destinations. However, `@SendToUser` when no user is identified behaves like `broadcast=false`: only the session that sent the message is targeted.

If you need to send to all devices of a user, ensure every session is associated with the same authenticated Principal.

## 5. End-to-End Experiment with Two Sessions for Alice

Goals of the test:

1. Create two independent STOMP connections both authenticated as `alice`.
2. Create a third connection authenticated as `bob`.
3. Have all three subscribe to `/user/queue/notifications`.
4. Send a notification from `SimpMessagingTemplate` to Alice and verify both of Alice's sessions receive it.
5. Send a message via default `@SendToUser` and verify both sessions receive it.
6. Send a message via `broadcast=false` and verify only the originating session receives it.
7. Disconnect one of Alice's sessions, verify the registry retains one session, and push again only to the remaining session.

Use a real client and embedded server to test the full WebSocket/STOMP path instead of calling controller methods directly. Spring distinguishes server-side tests from end-to-end tests; this exercise requires end-to-end because multi-session behavior depends on the handshake Principal, session registry, subscriptions, and user-destination resolver.

### 5.1. Test Dependencies

The example uses Java 17+, Spring Boot 3.4+ / Spring Framework 6.2+, and JUnit 5. In Maven, rely on Spring Boot's dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-websocket</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.awaitility</groupId>
        <artifactId>awaitility</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring Boot manages compatible versions of Spring Framework, WebSocket, and JUnit. Awaitility is used to wait for subscriptions to appear in the registry without using `Thread.sleep`.

### 5.2. Test Application: Assigning a Distinct Principal per Handshake

In production, the Principal must come from real authentication, typically an HTTP handshake protected by Spring Security. In the test, we use a test-only header to simulate three clients with two different usernames.

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.support.DefaultHandshakeHandler;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@SpringBootConfiguration
@EnableAutoConfiguration
@EnableWebSocketMessageBroker
static class TestApplication implements WebSocketMessageBrokerConfigurer {

    @Bean
    NotificationController notificationController() {
        return new NotificationController();
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setHandshakeHandler(new DefaultHandshakeHandler() {
                    @Override
                    protected Principal determineUser(
                            ServerHttpRequest request,
                            WebSocketHandler wsHandler,
                            Map<String, Object> attributes) {

                        String username =
                                request.getHeaders().getFirst("X-Test-User");

                        if (username == null || username.isBlank()) {
                            return null;
                        }

                        return () -> username;
                    }
                });
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/queue");
    }
}
~~~

This configuration is strictly for testing. Do not use the `X-Test-User` header as a production authentication mechanism: clients can set that value themselves. In a real application, use a Principal verified during the HTTP handshake, session, or token authentication per your security configuration.

### 5.3. Controller with Two Send Styles

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
class NotificationController {

    @MessageMapping("/notify-all")
    @SendToUser("/queue/notifications")
    public String notifyAllSessions(String message) {
        return message;
    }

    @MessageMapping("/notify-current")
    @SendToUser(
            destinations = "/queue/notifications",
            broadcast = false)
    public String notifyCurrentSession(String message) {
        return message;
    }
}
~~~

The two methods differ only in `broadcast`. The first sends to all sessions of the Principal processing the message; the second restricts the result to the session that sent the message.

### 5.4. Integration Test with WebSocketStompClient

The test below creates three STOMP client sessions. The first two have Principal `alice`; the third has Principal `bob`.

~~~java
import java.lang.reflect.Type;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.messaging.converter.StringMessageConverter;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.messaging.simp.user.SimpUser;
import org.springframework.messaging.simp.user.SimpUserRegistry;
import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

import static java.util.concurrent.TimeUnit.SECONDS;
import static org.junit.jupiter.api.Assertions.*;

import static org.awaitility.Awaitility.await;

@SpringBootTest(
        classes = UserDestinationMultiSessionTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class UserDestinationMultiSessionTest {

    @LocalServerPort
    int port;

    @Autowired
    SimpMessagingTemplate messagingTemplate;

    @Autowired
    SimpUserRegistry userRegistry;

    private WebSocketStompClient stompClient;
    private final List<StompSession> sessions = new ArrayList<>();

    @BeforeEach
    void setUp() {
        stompClient = new WebSocketStompClient(
                new StandardWebSocketClient());
        stompClient.setMessageConverter(new StringMessageConverter());
        stompClient.start();
    }

    @AfterEach
    void tearDown() {
        for (StompSession session : sessions) {
            if (session.isConnected()) {
                session.disconnect();
            }
        }
        stompClient.stop();
    }

    @Test
    void sendsToAllUserSessionsAndCanReplyOnlyToOrigin() throws Exception {
        StompSession aliceBrowser = connect("alice");
        StompSession aliceMobile = connect("alice");
        StompSession bobBrowser = connect("bob");

        BlockingQueue<String> browserInbox = new LinkedBlockingQueue<>();
        BlockingQueue<String> mobileInbox = new LinkedBlockingQueue<>();
        BlockingQueue<String> bobInbox = new LinkedBlockingQueue<>();

        aliceBrowser.subscribe(
                "/user/queue/notifications", frameHandler(browserInbox));
        aliceMobile.subscribe(
                "/user/queue/notifications", frameHandler(mobileInbox));
        bobBrowser.subscribe(
                "/user/queue/notifications", frameHandler(bobInbox));

        // Wait until all three sessions and their subscriptions are registered.
        await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
            assertUserReady("alice", 2);
            assertUserReady("bob", 1);
        });

        // 1. A service push to Alice reaches both Alice sessions.
        messagingTemplate.convertAndSendToUser(
                "alice", "/queue/notifications", "service-push");

        assertEquals("service-push", browserInbox.poll(5, SECONDS));
        assertEquals("service-push", mobileInbox.poll(5, SECONDS));
        assertNull(bobInbox.poll(300, TimeUnit.MILLISECONDS));

        // 2. Default @SendToUser also reaches all subscribed Alice sessions.
        aliceBrowser.send("/app/notify-all", "controller-broadcast");

        assertEquals("controller-broadcast", browserInbox.poll(5, SECONDS));
        assertEquals("controller-broadcast", mobileInbox.poll(5, SECONDS));
        assertNull(bobInbox.poll(300, TimeUnit.MILLISECONDS));

        // 3. broadcast=false returns only to the originating session.
        aliceBrowser.send("/app/notify-current", "current-session-only");

        assertEquals("current-session-only", browserInbox.poll(5, SECONDS));
        assertNull(mobileInbox.poll(500, TimeUnit.MILLISECONDS));
        assertNull(bobInbox.poll(500, TimeUnit.MILLISECONDS));

        // 4. After the mobile session disconnects, the registry has one Alice session.
        aliceMobile.disconnect();

        await().atMost(Duration.ofSeconds(5)).untilAsserted(
                () -> assertUserReady("alice", 1));

        messagingTemplate.convertAndSendToUser(
                "alice", "/queue/notifications", "after-disconnect");

        assertEquals("after-disconnect", browserInbox.poll(5, SECONDS));
        assertNull(bobInbox.poll(300, TimeUnit.MILLISECONDS));
    }

    private StompSession connect(String username) throws Exception {
        WebSocketHttpHeaders headers = new WebSocketHttpHeaders();
        headers.add("X-Test-User", username);

        StompSession session = stompClient.connectAsync(
                "ws://localhost:" + port + "/ws",
                headers,
                new StompSessionHandlerAdapter() {
                }).get(5, SECONDS);

        sessions.add(session);
        return session;
    }

    private void assertUserReady(String username, int expectedSessions) {
        SimpUser user = userRegistry.getUser(username);

        assertNotNull(user);
        assertEquals(expectedSessions, user.getSessions().size());
        assertTrue(user.getSessions().stream()
                .allMatch(session -> session.getSubscriptions().size() == 1));
    }

    private StompFrameHandler frameHandler(BlockingQueue<String> inbox) {
        return new StompFrameHandler() {
            @Override
            public Type getPayloadType(StompHeaders headers) {
                return String.class;
            }

            @Override
            public void handleFrame(StompHeaders headers, Object payload) {
                inbox.add((String) payload);
            }
        };
    }
}
~~~

This is an integration test class for Spring Boot 3.4+ / Spring Framework 6.2+, not a standalone Java file run with `javac`. The test requires an embedded WebSocket server and the dependencies in section 5.1. It can be run in a Maven project with:

~~~bash
mvn -Dtest=UserDestinationMultiSessionTest test
~~~

The test does not use `Thread.sleep`. Awaitility waits for the user registry to record all sessions/subscriptions; `BlockingQueue.poll(timeout)` waits for messages with an explicit deadline. For negative assertions, a short wait confirms other sessions do not receive a frame within the observation window.

The simple broker does not support STOMP RECEIPT to confirm SUBSCRIBE has been processed by the broker. Therefore, the test waits for `SimpUserRegistry` to show the subscription before sending. If using a broker relay that supports receipts, you can enable receipts on the client and await the `StompSession.Subscription` callback instead of polling the registry.

### 5.5. Expected Results

| Action | Alice browser | Alice mobile | Bob browser |
|---|---|---|---|
| `convertAndSendToUser("alice", ...)` | Received | Received | Not received |
| Default `@SendToUser` | Received | Received | Not received |
| `@SendToUser(broadcast=false)` from browser | Received | Not received | Not received |
| After mobile disconnects | Receives new push | Disconnected | Not received |

The test also verifies that when the mobile session closes, `SimpUserRegistry` retains one session for Alice. When sending the next push, only the active session receives the message.

## 6. Why Wait for Subscriptions to Be Ready?

Calling `session.subscribe(...)` only sends a STOMP SUBSCRIBE frame. It does not guarantee the broker has finished registering the subscription at the exact moment the next line of code runs.

If a notification is sent immediately after subscribing, tests can suffer a race condition:
- The test sends a push before the broker processes SUBSCRIBE.
- One session receives the message while the other has not finished registering yet.
- The test passes or fails intermittently depending on machine speed and scheduling.

With the built-in simple broker, STOMP RECEIPT is not supported. You can wait for `SimpUserRegistry` to show the session and subscription as in the example above, or use an `ExecutorChannelInterceptor` on the broker channel to signal after the subscription is processed.

Do not solve races with `Thread.sleep(500)`. Sleeping does not prove the subscription is ready and makes tests sensitive to wall-clock timing.

## 7. Observing the Session Lifecycle

Spring publishes ApplicationContext events useful for tracking sessions:

- `SessionConnectEvent`: STOMP CONNECT received; the event carries the session ID and user information if present.
- `SessionConnectedEvent`: broker returned CONNECTED; the STOMP session is considered fully established.
- `SessionSubscribeEvent`: client created a subscription.
- `SessionUnsubscribeEvent`: client canceled a subscription.
- `SessionDisconnectEvent`: STOMP session ended.

You can use these events to update online session counts, active devices, connection timestamps, and subscription state. `SessionDisconnectEvent` can be published multiple times for the same session in some scenarios; cleanup logic must be idempotent.

Example listener recording sessions:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
class StompSessionAudit {

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        var accessor =
                SimpMessageHeaderAccessor.wrap(event.getMessage());

        String sessionId = accessor.getSessionId();
        String username = accessor.getUser() != null
                ? accessor.getUser().getName()
                : "anonymous";

        // Record sessionId, username, and connectedAt.
    }

    @EventListener
    public void onDisconnected(SessionDisconnectEvent event) {
        var accessor =
                SimpMessageHeaderAccessor.wrap(event.getMessage());

        String sessionId = accessor.getSessionId();

        // Remove session if it still exists; operation must be idempotent.
    }
}
~~~

Do not maintain a separate registry if `SimpUserRegistry` already meets your requirements. If you need to store device info, browser name, or device ID, store authenticated metadata separately and associate it with the session ID; do not use a client-sent device ID as proof of identity.

## 8. Multiple Application Nodes and Broker Relay

In a single application instance, `DefaultSimpUserRegistry` knows about user sessions connected to that instance. When deploying multiple nodes, Alice may connect to node A with her browser and node B with her phone. If the node sending a message only knows its local registry, it may not find sessions residing on other nodes.

With a STOMP broker relay, Spring supports sharing the registry and forwarding unresolved user destinations:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setUserRegistryBroadcast("/topic/simp-user-registry")
            .setUserDestinationBroadcast("/topic/unresolved-user-destination");
}
~~~

- `setUserRegistryBroadcast`: broadcasts local user registry information and receives registries from other nodes, helping each node know where user sessions reside.
- `setUserDestinationBroadcast`: broadcasts user destination messages not resolved by the current node so other nodes get a chance to handle them.

These broadcast destinations must be secured and reserved strictly for infrastructure. Do not let clients publish to them arbitrarily. The broker relay needs connection details, credentials, and heartbeats configured appropriately for the actual broker.

The built-in simple broker is suitable for single-process testing; it does not synchronize session registries across multiple nodes. Do not assume placing an application behind a load balancer is enough for user destinations to automatically find sessions across every instance.

### 8.1. Managing Per-Session Queues on an External Broker

When using an external broker, user destinations may be mapped to per-session private destinations. Check broker documentation on deleting queues with no remaining consumers or closed sessions. For example, some RabbitMQ setups use auto-delete queues; ActiveMQ has mechanisms to purge inactive destinations.

If per-session queues are not cleaned up, the broker may accumulate stale destinations. If cleaned up too early, in-flight messages or reconnecting sessions may be impacted. Choose a policy aligned with your broker's semantics and retention.

## 9. Authorization and Security

User destinations do not replace authorization.

1. **Principals must come from server-side authentication.** In HTTP/WebSocket applications, Spring uses the Principal bound to the handshake. Do not trust a username in the payload or an arbitrary STOMP header.
2. **Do not let clients send to another user's destination.** Configure Spring Security message authorization to check destinations, commands, and user permissions.
3. **Services must specify the right username.** `convertAndSendToUser` should receive a username derived from a domain event or authentication result, not from an unchecked request field.
4. **Do not broadcast sensitive data to all sessions unnecessarily.** Default broadcasting suits state synchronization; operation-specific sensitive info should be session-scoped or use dedicated destination designs.
5. **Control subscriptions.** Clients must not be allowed to subscribe to a destination just because they know a username or queue name.
6. **Protect internal destinations.** User-registry broadcast and unresolved-destination broadcast destinations must be reserved solely for the broker relay.
7. **Limit sessions and rates.** One account can open multiple sessions; apply reasonable limits to prevent resource abuse and keep device counts bounded.

Spring Security supports authorization for WebSocket sub-protocols via `ChannelInterceptor`. Enforce policies across CONNECT, SUBSCRIBE, SEND, and messages to application/broker prefixes according to system rules.

## 10. Diagnosing Issues When Multiple Sessions Fail to Receive Messages Properly

### 10.1. Only One of Alice's Two Sessions Receives It

Check:
- Do both handshakes have the same Principal name?
- Are both sessions still actually connected?
- Have both subscribed to `/user/queue/notifications`?
- Does the message sent via `convertAndSendToUser` have the right username and destination?
- Is the second session on another node, and is user registry broadcast configured?

### 10.2. Bob Also Receives Alice's Notifications

Check:
- Are you accidentally sending to `/topic/notifications` instead of a user destination?
- Is the user destination being processed directly by the broker due to misconfigured prefixes?
- Are connection Principals being shared or spoofed?
- Is the service broadcasting to a public destination?

### 10.3. broadcast=false Still Sends to Other Devices

Check whether the annotation is actually placed on the method handling the message, and whether the response is being sent via a separate `SimpMessagingTemplate.convertAndSendToUser` call inside a service. `broadcast=false` only restricts messages sent within the session context of the message being handled; it does not automatically restrict every other push in the same business flow.

### 10.4. Session Closed but Remains in Registry

Check whether WebSocket close was detected, whether the listener handling `SessionDisconnectEvent` ran, and whether any exception occurred during cleanup. The event may fire multiple times, so cleanup must be idempotent and must not decrement/delete state multiple times.

### 10.5. Works on One Node but Fails When Scaling Horizontally

Check the local `SimpUserRegistry` vs. multi-server registry, broker relay, `userRegistryBroadcast`, `userDestinationBroadcast`, destination ACLs, and broker topology. Try connecting two clients for the same user to two different application instances to reproduce the bug.

## 11. Expanding the Test Suite

After the basic test, add cases for:

- A user with 1, 2, 5, or more sessions; verify actual session counts and fan-out.
- Two users subscribing to the same logical destination; verify no cross-delivery.
- One session unsubscribes while staying connected; that session stops receiving messages for the unsubscribed destination.
- One session disconnects; the registry updates the remaining session count.
- All sessions disconnect; the user is no longer in the registry.
- Unconnected user; verify service pushes are not mistaken for offline-persisted messages.
- A session reconnects with a new session ID; verify the registry does not retain the old session.
- Exception handler returns an error with `broadcast=false`; only the client causing the error receives the alert.
- Broker relay loses connection; test `BrokerAvailabilityEvent`, send failures, and reconnect behavior.
- Two application nodes; test registry broadcast and unresolved destination routing.
- Multiple sessions sending concurrently; verify message ID/correlation ID and handler idempotency.

In multi-client end-to-end tests, close sessions, unsubscribe, and stop `WebSocketStompClient` in cleanup so no lingering connections or heartbeat tasks leak between tests.

## 12. Production Checklist

- [ ] Every WebSocket session is bound to an authenticated Principal.
- [ ] Clients subscribe to logical user destinations such as `/user/queue/notifications`.
- [ ] Server sends user pushes via `convertAndSendToUser(username, destination, payload)`.
- [ ] Explicitly decided whether notifications go to all sessions or only the originating session.
- [ ] `@SendToUser` defaults to broadcasting to all subscribed sessions.
- [ ] `broadcast=false` is used for replies intended only for the session handling the request.
- [ ] User destinations are not treated as an offline inbox or durable notification store.
- [ ] Authorization policies cover CONNECT, SUBSCRIBE, and SEND.
- [ ] Session/concurrency limits and connection lifecycle monitoring are in place.
- [ ] Session cleanup on disconnect events is idempotent.
- [ ] When scaling to multiple nodes, user registry broadcast and unresolved destination broadcast are configured with broker relay.
- [ ] Broker cleans up per-session destinations/queues when no longer in use.
- [ ] Integration tests include two sessions with the same Principal and another user as an isolation control.

## References

- Spring Framework Reference — User Destinations, multi-session behavior, `@SendToUser`, and `convertAndSendToUser`: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- Spring Framework Reference — Enable STOMP, application/broker prefixes, and endpoint configuration: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html
- Spring Framework Reference — Testing STOMP over WebSocket, server-side and end-to-end tests: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/testing.html
- Spring Framework Reference — STOMP Client and `WebSocketStompClient`: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html
- Spring Framework Reference — Annotated Controllers, `@MessageMapping`, `@SendToUser`, and exception handlers: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html
- Spring Framework Reference — STOMP ApplicationContext Events: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html
- Spring Framework Javadoc — `SimpUserRegistry`, `SimpUser`, `SimpSession`, and `SimpSubscription`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/package-summary.html
- Spring Framework Javadoc — `StompBrokerRelayRegistration` multi-server registry broadcast: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html
