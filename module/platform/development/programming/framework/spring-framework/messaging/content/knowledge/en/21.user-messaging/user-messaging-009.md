# User Destinations When Unauthenticated or Running Multiple Servers

Spring WebSocket supports sending messages to a specific user through user destinations. The client subscribes to a logical destination such as /user/queue/notifications; the server sends a message to a principal with SimpMessagingTemplate or returns from a controller annotated with @SendToUser. Spring resolves the logical destination into a physical destination bound to the corresponding WebSocket session.

This mechanism needs to be understood across two different scenarios:

- When the client already has a Principal, Spring can group multiple sessions of the same user and send to one or all sessions according to policy.
- When the client is not yet authenticated, Spring can still send a reply back to the exact session that sent the request. To proactively push to a guest later, the application must issue a server-controlled session/guest identifier.
- When the application runs across multiple servers, each server only knows the sessions it manages. It must share user registry information and forward unresolved messages through a shared broker.

## 1. What problem do user destinations solve?

Suppose Alice opens the website in two tabs. Both tabs subscribe to /user/queue/notifications. A service sends a notification to Alice:

~~~java
messagingTemplate.convertAndSendToUser(
    "alice",
    "/queue/notifications",
    notification
);
~~~

The application does not need to manually append the session ID to the destination. Spring looks up the active sessions belonging to user alice and translates the logical destination into a private destination for each session. One form of physical destination might look like /queue/notifications-user{sessionId}; the specific suffix is generated and managed by Spring.

The client always subscribes to the logical destination:

~~~javascript
client.subscribe("/user/queue/notifications", (frame) => {
  const notification = JSON.parse(frame.body);
  renderNotification(notification);
});
~~~

The client does not need to know the session ID or physical destination. Do not hard-code the resolved destination name after Spring processes it, because it depends on the session and internal framework mechanics.

User destinations differ from public topics. A message sent to /topic/announcements is routed to subscribers of that topic. A message sent to /user/queue/notifications is resolved based on the user's identity and their active sessions.

## 2. Basic user destination configuration

Example configuration of a Spring WebSocket application using the Simple Broker:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }
}
~~~

Each prefix has a different role:

- /app: messages from clients are routed to application handlers such as @MessageMapping.
- /topic and /queue: destinations handled by the broker.
- /user: logical prefix for Spring to recognize and resolve user destinations.
- /ws: HTTP endpoint used to initiate the WebSocket/STOMP connection.

The Simple Broker is suitable for examples or single-node deployments with simple requirements. It stores subscriptions in application memory and does not share state across multiple instances. Multi-server configuration is covered in a later section.

## 3. Sending to an authenticated user

In a typical WebSocket flow, Spring uses the Principal attached during the HTTP handshake to identify the user. This Principal usually comes from the application's HTTP authentication mechanism. When a STOMP message is processed, the controller can receive Principal as a parameter.

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class PrivateMessageController {

    @MessageMapping("/profile.refresh")
    @SendToUser("/queue/replies")
    public ProfileReply refresh(ProfileRequest request, Principal principal) {
        return new ProfileReply(
            principal.getName(),
            request.requestId(),
            "REFRESH_ACCEPTED"
        );
    }

    public record ProfileRequest(String requestId) {}

    public record ProfileReply(
        String username,
        String requestId,
        String status
    ) {}
}
~~~

The client sends a request to /app/profile.refresh and subscribes to /user/queue/replies. With an authenticated Principal, @SendToUser sends by default to all active sessions associated with the same user. If Alice has two tabs open, both tabs can receive the reply.

To send the reply only to the session that sent the request, set broadcast=false:

~~~java
@MessageMapping("/profile.refresh")
@SendToUser(value = "/queue/replies", broadcast = false)
public ProfileReply refreshCurrentTab(ProfileRequest request) {
    return new ProfileReply(
        request.requestId(),
        "REFRESH_ACCEPTED"
    );
}

public record ProfileRequest(String requestId) {}

public record ProfileReply(String requestId, String status) {}
~~~

The two usages have different meanings:

| Configuration | Recipient scope |
|---|---|
| @SendToUser("/queue/replies") | All sessions of the current Principal |
| @SendToUser(value="/queue/replies", broadcast=false) | Only the session that sent the message being processed |

Choose based on business intent. A reply confirming an operation on the current tab typically fits broadcast=false. Notifications of profile or account status changes may need to go to all of the user's sessions.

## 4. Proactive message sending from a service

When a service needs to send a notification outside the return flow of a @MessageMapping handler, use SimpMessagingTemplate.

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String principalName, Notification event) {
        messagingTemplate.convertAndSendToUser(
            principalName,
            "/queue/notifications",
            event
        );
    }

    public record Notification(String eventId, String message) {}
}
~~~

The principalName value must match the recipient's Principal.getName(). In a real application, the service should obtain the principal name from the authenticated context or validated business data. Do not take an arbitrary username from the client payload and send a message to that account; doing so can create a cross-user message injection vulnerability.

Client subscribes:

~~~javascript
client.subscribe("/user/queue/notifications", (frame) => {
  const event = JSON.parse(frame.body);
  showToast(event.message);
});
~~~

convertAndSendToUser sends to sessions currently associated with the principal in the registry. This call does not prove the browser received the frame or that the callback finished running. If business logic requires confirmation, define a separate ACK and persist the corresponding state.

## 5. User destinations when unauthenticated

A connection without a Principal may still need to receive private replies, for example:

- A login page sends a status check request before the user logs in.
- A guest sends a request to preview public data.
- A client sends a temporary command and needs to receive the result on that same tab.
- An unlogged-in device needs to receive the outcome of an operation it just submitted.

For a message arriving from that session itself, you can use @SendToUser with broadcast=false:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class GuestMessageController {

    @MessageMapping("/guest.preview")
    @SendToUser(value = "/queue/replies", broadcast = false)
    public PreviewReply preview(PreviewRequest request) {
        return new PreviewReply(
            request.requestId(),
            "PREVIEW_READY"
        );
    }

    public record PreviewRequest(String requestId) {}

    public record PreviewReply(String requestId, String status) {}
}
~~~

The client subscribes to /user/queue/replies before sending a message to /app/guest.preview. Spring can route the reply back to the requesting session even if the session has no authenticated user. For anonymous sessions, @SendToUser is handled scoped to the session, equivalent to broadcast=false; writing broadcast=false explicitly in code makes intent clear and avoids confusion when reading.

The key point is that an unauthenticated session has no trusted username that a service can use as a long-term recipient identifier. Therefore:

- Direct replies for the request currently being processed can use @SendToUser(broadcast=false).
- Do not use a client-declared username to call convertAndSendToUser.
- Do not treat a session ID as an authenticated user identity.
- If proactive messages must be sent to a guest after the initial request completes, the application needs to manage a server-issued guest/session identifier and bind it to the WebSocket session.

## 6. Issuing a server-controlled guest identifier

Some applications need to send notifications to guests without requiring an account. A temporary Principal can be attached per WebSocket session. This Principal does not prove real identity; it is merely a server-generated routing key.

Example handshake handler that keeps the existing Principal if the request is already authenticated, while assigning a random ID to guest connections:

~~~java
import java.security.Principal;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.server.ServerHttpRequest;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.support.DefaultHandshakeHandler;

public class GuestAwareHandshakeHandler extends DefaultHandshakeHandler {

    @Override
    protected Principal determineUser(
            ServerHttpRequest request,
            WebSocketHandler wsHandler,
            Map<String, Object> attributes) {

        Principal authenticated = request.getPrincipal();
        if (authenticated != null) {
            return authenticated;
        }

        String guestId = "guest-" + UUID.randomUUID();
        return () -> guestId;
    }
}
~~~

Register the handler on the endpoint:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
        .setHandshakeHandler(new GuestAwareHandshakeHandler());
}
~~~

After the handshake, the service can use the guest Principal name attached to the session:

~~~java
messagingTemplate.convertAndSendToUser(
    guestPrincipalName,
    "/queue/notifications",
    guestNotification
);
~~~

Here, guestPrincipalName must be obtained from the Principal or from a server-side mapping, not from an arbitrary username field in the client's message.

A new UUID on every connection means the guest identity exists only for that session. Upon reconnect, the client will get a new ID. If the product requires guests to preserve state across reconnects, use a signed random guest token or an opaque server-issued code, verify the token before the handshake, and map it to a Principal. Do not use an email, phone number, or client-chosen ID as a routing key without verification and access control.

Guest identities must also have restricted permissions. A guest Principal should not automatically gain permission to read private data, subscribe to other users' destinations, or send messages to administrative destinations.

## 7. Why single-server configuration is insufficient when running multiple servers

Suppose the system has two instances:

- Alice connects via WebSocket to Server A.
- A background task running on Server B calls convertAndSendToUser("alice", ...).
- Server B does not have Alice's session in its local user registry.

If relying only on each node's in-memory registry, Server B may fail to resolve the user destination. Even if both nodes point to the same broker, the broker does not automatically know which instance principal alice is connected to unless the application shares user routing information.

A multi-node system needs two capabilities:

1. Sharing information about connected users/sessions across nodes so the sending node can find where the recipient is.
2. Forwarding user destination messages that the current node could not resolve so another node has a chance to handle them.

Spring supports two broadcast destinations for this: user registry broadcast and unresolved user destination broadcast.

## 8. Multi-server configuration with broker relay

Instances must share an external STOMP broker, such as a broker supporting STOMP relay. Each instance configures the same broker prefixes and the two broadcast destinations.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.messaging.simp.config.StompBrokerRelayRegistration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class ClusterWebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");

        StompBrokerRelayRegistration relay =
            registry.enableStompBrokerRelay("/topic", "/queue");

        relay.setUserRegistryBroadcast("/topic/simp-user-registry");
        relay.setUserDestinationBroadcast("/topic/unresolved-user");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }
}
~~~

The two broadcast destinations have distinct responsibilities:

- **userRegistryBroadcast** broadcasts the node's registry information so other nodes know which users/sessions are connected where. Spring combines local information and information received from other nodes to resolve user destinations.
- **userDestinationBroadcast** forwards messages that the current node cannot resolve to other nodes. The node holding the recipient's session can resolve that message into the corresponding physical destination.

Nodes must use the same broker and agree on the broadcast destination names. The broker relay must be configured with the host, port, credentials, and access rights appropriate for the environment. Secrets should be loaded from secure configuration or a secret store, not hard-coded in source code.

The two broadcast destinations are internal channels between application nodes. Do not grant browser clients arbitrary subscribe or publish permissions to /topic/simp-user-registry or /topic/unresolved-user. Configure broker ACLs and Spring Security to protect them.

## 9. Routing flow when the user is connected to another node

Suppose Alice is connected to Server B, while business logic on Server A wants to send a notification:

1. Alice opens a WebSocket to Server B and subscribes to /user/queue/notifications.
2. Server B records the Principal and session in its local user registry.
3. Server B's registry information is broadcast over userRegistryBroadcast.
4. Server A receives the update and learns that Alice has a session on Server B.
5. Server A sends the message to Alice's logical user destination.
6. The user destination handler resolves the message into a private destination for Alice's session.
7. The broker relay forwards the message through the shared broker to the connection managed by Server B.
8. Server B delivers the STOMP MESSAGE to the client.

If Server A does not yet have sufficient information to resolve the recipient, userDestinationBroadcast allows broadcasting the unresolved message so other nodes can attempt to process it. If no node holds a matching session, the message has no recipient. User destinations do not automatically create a durable mailbox for offline users.

Registry information exchanged between nodes can experience latency. Therefore, newly created or recently closed connections can create a window where the registry does not yet reflect the latest state. For critical business notifications, persist events in a database/outbox and implement retry or resync mechanisms instead of treating broadcast as the final delivery guarantee.

## 10. Distinguishing Simple Broker, broker relay, and user registry

| Component | Role | Limitation to remember |
|---|---|---|
| Spring Simple Broker | Manages subscriptions and routing within a single application | In-memory state; does not share subscriptions across servers |
| STOMP broker relay | Forwards messages from Spring to an external broker and vice versa | Requires operating the broker, configuring connections, and managing access control |
| SimpUserRegistry | Tracks Principals and sessions known to the node | Local registry does not automatically know sessions on other nodes |
| userRegistryBroadcast | Shares user/session information between nodes | Distributed information has propagation delay |
| userDestinationBroadcast | Forwards user destinations that the current node cannot resolve | Does not create durable storage for offline users |

Cross-instance user destination routing cannot be achieved merely by placing instances behind a load balancer. Sticky sessions can keep a client's connection on the same node, but they do not help another node know where the session lives when it sends a notification. The system still needs a routing mechanism or an explicitly designed storage/dispatch layer.

## 11. Security and common design mistakes

**Using a client-sent user name.** Clients can spoof the username in the payload. Obtain identity from the authenticated Principal or a server-issued guest identity.

**Confusing broadcast=true with sending to a single tab.** A user can have multiple sessions across multiple devices. Use broadcast=false for replies belonging strictly to the current request/session.

**Using default @SendToUser for anonymous requests.** Anonymous sessions have no stable user identity. Specify broadcast=false explicitly so the reply goes back only to the requesting session.

**Using convertAndSendToUser for a guest without a Principal.** The service has no trusted username to look up. Use session-scoped replies or issue a server-managed guest Principal/mapping.

**Using the Simple Broker for multiple nodes.** Each node has its own registry and subscriptions. Use a broker relay with a shared broker and configure the required broadcasts.

**Allowing browsers to access internal broadcast destinations.** User registry and unresolved messages contain internal routing details. Protect destinations with ACLs and authorization.

**Assuming user destinations guarantee delivery.** If the user is offline, there is no session to resolve. Persist required events and provide a sync/replay mechanism.

**Not handling multiple sessions.** One account can open multiple tabs or devices. Decide explicitly whether to send to all sessions or only the requesting session.

**Not handling reconnects.** A new session ID may be created after reconnecting; per-session random guest identities also change. Re-register subscriptions and sync necessary data.

## 12. Testing key scenarios

An integration test suite should verify the following cases:

1. An authenticated user subscribes to /user/queue/notifications and receives messages sent with convertAndSendToUser.
2. The same user opens two sessions; default broadcast sends to both.
3. A handler uses broadcast=false; only the session that issued the request receives the reply.
4. An anonymous client sends a request and receives a reply via @SendToUser(broadcast=false).
5. An anonymous client cannot choose someone else's Principal name or username via the payload.
6. A server-issued guest Principal only receives notifications bound to that corresponding guest session.
7. A user connects on Server B while the message is published from Server A; registry broadcast helps locate the right node.
8. A node unable to resolve a user destination broadcasts the unresolved message and the node holding the session processes it.
9. The user disconnects before sending; the system observes there is no receiving session and important data can still be resynced.
10. Reconnect creates a new session; the client re-subscribes and restores state per the application contract.

In multi-node tests, at least two application instances must be run alongside a real broker relay. A unit test on a single Simple Broker does not prove that user registry broadcast or unresolved destination broadcast works across servers.

## 13. Diagnostic checklist

When a user does not receive messages, check in order:

- Did the client subscribe to the right logical destination /user/queue/... before the server sent the message?
- Does the handshake have a Principal? Does Principal.getName() match the exact value the service passes to convertAndSendToUser?
- Was the message sent to the right sub-destination, e.g., /queue/notifications, without adding /user to the destination parameter of convertAndSendToUser?
- If anonymous, was the message returned from an inbound handler with broadcast=false?
- If a guest needs proactive pushes, is the guest Principal/session mapping still valid and server-controlled?
- Is the application running multiple nodes while still using the Simple Broker?
- Do all nodes share the same broker relay and the same broadcast destinations?
- Do broker ACLs allow application nodes to publish/subscribe to internal destinations?
- Does the user registry contain an active session? Is there latency from connect/disconnect or reconnect?
- Are there event IDs and per-hop logs to distinguish destination resolution errors from transport/client callback errors?

User destinations let applications send messages by identity or session instead of managing physical destinations manually. For anonymous sessions, restrict replies to the session or issue a server-managed guest identity. For multiple servers, combine a broker relay, user registry broadcast, and unresolved destination broadcast; notifications requiring guarantees must have dedicated storage and recovery mechanisms.