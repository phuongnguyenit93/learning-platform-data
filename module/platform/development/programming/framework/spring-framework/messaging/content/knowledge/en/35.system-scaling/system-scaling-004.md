# User Registry and User Destinations in a Spring Messaging Cluster

In Spring STOMP applications, user destinations let you send messages to sessions belonging to a user without requiring clients to know physical queue names. When the application runs across multiple application servers, each node directly manages only the WebSocket sessions connected to that node. To reach the right user even when they are connected to another node, Spring provides `SimpUserRegistry`, `MultiServerUserRegistry`, `UserRegistryMessageHandler`, and two cluster broadcast mechanisms.

Key point: **user destination is the per-user/per-session routing layer; user registry is the data about currently connected users, sessions, and subscriptions.** In a cluster, registry broadcasts inform nodes about sessions on other nodes, while unresolved-destination broadcasts give other nodes a chance to handle messages that the current node could not resolve.

## 1. What Problem Do User Destinations Solve?

A client subscribes to a logical destination such as `/user/queue/notifications`. Spring recognizes the `/user/` prefix, and `UserDestinationMessageHandler` translates it into an actual destination with a session-specific suffix, for example `/queue/notifications-useri9oqdfzo`. Thanks to the per-session suffix, two users can subscribe to the same logical name without receiving each other's messages.

On the sending side, the application sends to `/user/{username}/queue/notifications`. Spring looks up that user's active sessions in `SimpUserRegistry`, then forwards the message to the destination corresponding to each session. `DefaultUserDestinationResolver` is the default resolver; it queries `SimpUserRegistry` to locate sessions and build one or more actual destinations.

```text
Client A (Principal alice)                 Spring application
SUBSCRIBE /user/queue/notifications  ----> UserDestinationMessageHandler
                                            |
                                            v
                                      SimpUserRegistry
                                            |
                                            v
                                      session id A-17
                                            |
                                            v
                                      /queue/notifications-userA17

Application service
convertAndSendToUser("alice", "/queue/notifications", payload)
                                            |
                                            v
                                      resolve alice sessions
                                            |
                                            v
                                      send to actual session destination
```

The `/user/...` path is a logical destination handled by Spring. The broker should not receive `/user` as an ordinary destination; configure application and broker prefixes properly so `UserDestinationMessageHandler` processes this prefix before messages reach the broker.

## 2. Components in the User Registry

| Component | Role |
| --- | --- |
| `SimpUserRegistry` | Abstraction storing connected users, each user's sessions, and subscriptions within each session |
| `SimpUser` | Represents a connected user; exposes the user's sessions |
| `SimpSession` | Represents a WebSocket/STOMP session |
| `SimpSubscription` | Represents a subscription belonging to a session |
| `UserDestinationResolver` | Translates a logical user destination into one or more actual destinations |
| `DefaultUserDestinationResolver` | Default resolver that looks up sessions via `SimpUserRegistry` |
| `UserDestinationMessageHandler` | Receives user-prefixed messages, resolves destinations, and forwards to the broker |
| `MultiServerUserRegistry` | Combines the local registry with remote registries received via broadcasts |
| `UserRegistryMessageHandler` | Periodically broadcasts local registry contents and receives registry broadcasts from other servers |

On a single node, the registry primarily reflects sessions created on that node. APIs such as `getUserCount()`, `getUsers()`, and `findSubscriptions(...)` are useful for diagnosing session/subscription state. Do not use the registry as an authentication source or user profile store; access permissions must still be checked using the security principal and authorization rules.

## 3. Why Is a Local Registry Not Enough in a Cluster?

Suppose two application servers A and B share one broker:

```text
alice's browser ---- WebSocket ----> App Server A
bob's browser   ---- WebSocket ----> App Server B

App Server A ---- STOMP broker relay ----+
                                         +---- Shared STOMP broker
App Server B ---- STOMP broker relay ----+
```

Node A knows Alice's sessions, but does not automatically know Bob's session on B. Node B knows Bob's session, but does not automatically know Alice's session on A. If a service on B calls `convertAndSendToUser("alice", ...)`, B's local registry may not find Alice. With only a local registry, the message may fail to reach the session connected on A.

In a multi-node environment, Spring can combine remote registries via `MultiServerUserRegistry`. `UserRegistryMessageHandler` sends snapshots of the local registry contents to the broker on a broadcast destination and listens for broadcasts from other nodes. Upon receiving a snapshot, `MultiServerUserRegistry` updates the set of remote registries it uses to look up users/sessions.

Registry broadcasting is a mechanism for sharing presence/session information between application servers. It does not synchronize business state, persist users long-term, or replace authentication. Registry data can lag between broadcast intervals; therefore, do not treat it as a distributed lock or a strongly consistent presence source.

## 4. Two Broadcasts with Different Responsibilities

Spring provides two separate configuration destinations on `StompBrokerRelayRegistration`:

| Setting | Broadcast Payload | Purpose |
| --- | --- | --- |
| `setUserRegistryBroadcast(...)` | Each node's local user registry contents | Inform other nodes of users/sessions/subscriptions connected to this node; aggregated inside `MultiServerUserRegistry` |
| `setUserDestinationBroadcast(...)` | Messages with user destinations not yet resolved by the current node | Give other nodes a chance to resolve the destination; the node holding the user's session can deliver the message |

For example, B receives a request to send to Alice, but its registry does not yet have the latest session info from A. With `userDestinationBroadcast`, B publishes the unresolved message to the broker. Other nodes receive the broadcast and attempt resolution; A holds Alice's session and can forward the message to that session. This handles cases where the registry has not caught up or the current node lacks user information.

Do not confuse the two settings: registry broadcast exchanges session metadata; unresolved-destination broadcast forwards a specific message so another node can attempt routing. The two destinations should be distinct, fanned out by the broker to all application nodes, and protected as internal channels.

## 5. Cluster Configuration with External STOMP Broker Relay

Spring's built-in simple broker runs in the memory of one application instance and is not suitable for clustering. With multiple application servers, use an external broker that supports STOMP and configure every node to relay to the same broker or shared broker cluster.

Java configuration example:

```java
@Configuration
@EnableWebSocketMessageBroker
public class ClusterWebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setUserRegistryBroadcast("/topic/internal-simp-user-registry")
                .setUserDestinationBroadcast("/topic/internal-unresolved-user");
    }
}
```

This snippet uses `enableStompBrokerRelay`, because `setUserRegistryBroadcast` and `setUserDestinationBroadcast` belong to `StompBrokerRelayRegistration`. Every node runs the same configuration, the same destination prefixes, and the same broker cluster. Replace relay host, credentials, and virtual host for your real environment; never leave default broker credentials in production.

`/topic/internal-simp-user-registry` and `/topic/internal-unresolved-user` are example names only. The broker must support fan-out to every node's subscriber. Do not use a competing-consumers queue where the broker delivers each message to only one consumer; broadcasts must reach every application server that may hold WebSocket sessions.

### 5.1. Conditions for This Configuration to Work

1. All application servers must relay to the same broker or a broker cluster capable of sharing the broadcast destinations.
2. Every node must configure the same `userRegistryBroadcast` and `userDestinationBroadcast` to publish and subscribe on the same destinations.
3. The broker must fan out registry snapshots and unresolved messages to all receiving nodes.
4. Every node must use the same rules for the user destination prefix, application prefix, and broker prefixes.
5. The `Principal` for the same user must produce the same destination username on every node.
6. Broker ACLs and Spring message authorization must restrict internal destinations; regular clients must not subscribe or publish to registry broadcasts.
7. Verify whether the broker automatically deletes per-session queues/destinations when sessions end or whether cleanup configuration is needed.

## 6. User Identity Must Be Consistent Across Nodes

`convertAndSendToUser(user, destination, payload)` looks up users by the name Spring obtains from `Principal` (or a destination username provider). Therefore, the same account must have the same identifier across all application servers. If node A sees the user as `alice` while node B sees `tenant-7:alice`, the registry and message sender may fail to match the same user.

If `Principal.getName()` is already globally unique, you can use it directly. If the principal name is only unique within a tenant or realm, implement `DestinationUserNameProvider` to supply a unique name dedicated to user destinations:

```java
public final class TenantPrincipal implements Principal, DestinationUserNameProvider {
    private final String subject;
    private final String tenantId;

    public TenantPrincipal(String subject, String tenantId) {
        this.subject = subject;
        this.tenantId = tenantId;
    }

    @Override
    public String getName() {
        return this.subject;
    }

    @Override
    public String getDestinationUserName() {
        return this.tenantId + ":" + this.subject;
    }
}
```

This is an illustrative class and must be constructed from a server-verified identity. `getDestinationUserName()` must return a stable, cluster-wide unique value; never use a string supplied directly by the client. When combining tenant and subject, ensure your encoding cannot collide across different pairs of values.

## 7. Sending Messages to a User

Client subscribes using the logical destination:

```javascript
stompClient.subscribe("/user/queue/notifications", frame => {
    const notification = JSON.parse(frame.body);
    renderNotification(notification);
});
```

Application service sends to an authenticated user:

```java
@Service
public class NotificationService {
    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String destinationUserName, Notification notification) {
        messagingTemplate.convertAndSendToUser(
                destinationUserName, "/queue/notifications", notification);
    }
}
```

`destinationUserName` must come from the authenticated identity or a server-validated user identifier. The `destination` passed to `convertAndSendToUser` does not need `/user/{username}` prepended; the template handles user routing. Clients simply subscribe to `/user/queue/notifications`.

With annotated controllers, `@SendToUser` sends responses to the user associated with the message being handled:

```java
@Controller
public class NotificationController {

    @MessageMapping("/notifications.ack")
    @SendToUser("/queue/acknowledgements")
    public AckResult acknowledge(AckCommand command, Principal principal) {
        return notificationService.acknowledge(principal.getName(), command);
    }
}
```

The controller snippet is illustrative; service and DTO classes are application-defined. The annotation destination is the suffix, without the `/user` prefix.

## 8. One User with Multiple Sessions

A user can open multiple tabs, multiple browsers, or multiple devices. `SimpUserRegistry` tracks multiple sessions for the same user; user destinations send by default to all sessions of that user subscribed to the destination.

- `@SendToUser("/queue/notifications")` broadcasts by default to all of the user's sessions that have a matching subscription.
- `@SendToUser(destinations = "/queue/errors", broadcast = false)` sends only to the session that originated the message being handled.
- `convertAndSendToUser(...)` routes to the user's active sessions; if targeting a single specific session is required, design explicit session-targeting and enforce session access control.

`broadcast=false` is useful for validation errors or responses specific to an action in the current tab. Notifications that should stay in sync across all of a user's devices typically use the default broadcast behavior. Choose semantics based on business requirements to avoid duplicate deliveries or leaking private responses to another session.

## 9. Session Lifecycle, Stale Registry, and Queue Cleanup

The registry reflects connected sessions and subscriptions observed by Spring. When a WebSocket closes, Spring emits a session disconnect event and updates the local registry. In a cluster, other nodes learn of the change only after receiving the next registry broadcast update. Thus, for a brief window, another node may still see a closed session or not yet see a new session.

Applications must handle stale presence cases:

- User has no remaining sessions: sending to a user destination may find no target. Decide explicitly whether the message is dropped, queued for later delivery, or persisted as a durable notification.
- Node dies abruptly: no normal disconnect event occurs; remote registries may retain the old snapshot for a bounded period. Monitor update timestamps and configure expiration/cleanup according to your Spring version.
- User reconnects to another node: a new session id is registered; new messages must resolve against the active session rather than relying on the old session.
- Broker holds physical per-session queues: verify the broker's auto-delete or purge mechanism. Spring documentation notes for example that RabbitMQ can create auto-delete queues with destinations like `/exchange/amq.direct/...`; ActiveMQ has options to purge inactive destinations.

Do not treat the user registry as a durable mailbox. If notifications must be received even when the user is offline, store them in a database or durable store and let the client fetch them after logging in. User destinations are primarily for delivery to active sessions.

## 10. Securing Destinations in a Cluster

Registry broadcasts and unresolved-destination broadcasts are internal traffic between application servers. They can contain usernames, sessions, subscriptions, and unresolved message payloads. Apply these measures:

- Use a dedicated broker account for the Spring relay's system connection; grant publish/subscribe permissions only to required destinations.
- Block regular STOMP clients from accessing `/topic/internal-simp-user-registry` and `/topic/internal-unresolved-user` via broker ACLs and message authorization.
- Never trust `username`, `tenantId`, or `destinationUserName` sent by clients in the body/headers. Determine the sender from the authenticated `Principal`.
- Check permissions for subscribing to each user destination and sending to other users; knowing a username does not imply permission to send messages.
- Protect application-to-broker connections with TLS and proper credentials; do not log registry contents or sensitive payloads.
- Limit payload sizes and broker topic access; unresolved broadcast must not become a bypass for clients to broadcast arbitrary messages cluster-wide.

User destinations are solely a routing mechanism. They do not replace authentication, authorization, tenant isolation, or business permission checks.

## 11. Multi-Node Testing

Testing with a single application server does not prove cluster configuration works. A useful integration test needs at least two Spring application instances and a shared STOMP broker.

### 11.1. Basic Scenarios

1. Start node A and node B with the same broker relay configuration and broadcast destinations.
2. Connect Alice's client to `/ws` on node A; subscribe to `/user/queue/notifications`.
3. Wait until the subscription is confirmed by the broker or the client receives a subscription-ready signal.
4. Invoke `NotificationService` on node B to send a message to Alice's destination username.
5. Verify the client connected to A receives the exact payload; clients of other users do not receive it.
6. Connect an additional session for Alice on node B and verify default delivery goes to matching sessions.
7. Test `broadcast=false` from one session and verify another session of the same user does not receive that response.

### 11.2. Failure and Recovery Scenarios

- Send to a user before the remote registry updates to confirm `userDestinationBroadcast` gives the session-holding node a chance to handle it.
- Shut down the node holding the session, wait for the registry update, and verify messages are no longer routed to the old session.
- Reconnect the user to another node and resend; verify the new destination is discovered.
- Temporarily stop and restore the broker; verify relay reconnection, registry broadcast resumption, and whether client sessions need to reconnect as designed.
- Attempt to subscribe/publish to internal broadcast destinations with an unauthorized client; verify the broker or Spring Security rejects it.
- Inspect broker queues/destinations after disconnect to confirm auto-delete/purge behavior.

Do not use fixed `Thread.sleep` calls to wait for registries or subscriptions in tests. Use receipts, latches, conditions, or Awaitility with bounded deadlines to wait for actual events. Log session id, node id, destination username, and correlation id in tests for diagnostics.

## 12. Observability and Diagnostics

To investigate cross-node routing, record at a minimum:

| Signal | Used to Diagnose |
| --- | --- |
| Node/server id | Identify which node received the connection and which sent the message |
| Destination username | Confirm user identity matches across nodes |
| User/session count per node | Detect registries missing sessions or holding stale sessions |
| Registry broadcasts received/sent and snapshot timestamp | Detect disrupted broker topic or registry synchronization |
| Unresolved user destination count | Detect nodes failing to locate local/remote targets |
| Broker availability and relay reconnects | Detect lost connectivity to the broker |
| Session connect/disconnect events | Track session lifecycle and cleanup |
| Queue/destination count on broker | Detect temporary queues not being deleted |

Do not put high-cardinality usernames, session ids, or destination usernames into metric tags. Use structured logs or traces to locate a specific user; metrics should use low-cardinality tags such as `node`, `outcome`, `broker`, and `destination_type`.

## 13. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Message sent from node B is not received by session on A | Local registry only, registry broadcast unconfigured, or not yet received | Use external broker relay and configure `setUserRegistryBroadcast` |
| Unresolved user destination does not reach other nodes | Missing unresolved broadcast or broker does not fan out topic | Configure `setUserDestinationBroadcast` and check broker subscriptions/ACLs |
| A user is not found despite being logged in | `Principal.getName()` or destination username differs across nodes | Standardize principal; use `DestinationUserNameProvider` when a global name is needed |
| `/user/...` message is treated by broker as a normal queue | Misconfigured prefixes or user-destination handler | Check application prefix, broker prefix, and user destination prefix |
| Response appears on all devices when only current tab needed it | Using `@SendToUser` default broadcast | Set `broadcast = false` for responses tied to the requesting session |
| Messages to offline user are lost | User destinations route only to active sessions | Persist notifications durably and let clients query on reconnect |
| User receives duplicate messages | Multiple broadcast paths or non-idempotent retry handling | Check registry/unresolved routing, broker topology, and message ids |
| Broker has many inactive queues | Per-session destinations are not cleaned up | Configure broker auto-delete/purge and verify lifecycle |

## 14. Takeaways

- `/user/queue/...` is a logical destination; Spring translates it into an actual per-session destination.
- `SimpUserRegistry` stores users, sessions, and subscriptions on a node; `DefaultUserDestinationResolver` uses the registry to resolve destinations.
- `MultiServerUserRegistry` combines the local registry with remote registry snapshots.
- `UserRegistryMessageHandler` publishes and receives registry broadcasts.
- `setUserRegistryBroadcast` shares registry information; `setUserDestinationBroadcast` forwards unresolved messages for other nodes to try.
- Use an external STOMP broker relay for multi-node setups; the in-memory simple broker is not suitable for clustering.
- The same user must have a stable, unique destination username across all nodes; use `DestinationUserNameProvider` if `Principal.getName()` is not unique enough.
- User destinations can send to multiple sessions of the same user by default; `broadcast=false` restricts `@SendToUser` responses to the current session.
- The registry holds temporary presence information, not a durable inbox or authorization source.
- Protect internal broadcast destinations with broker ACLs and message security; test with two real nodes and a shared broker.

## References

- [Spring Framework Reference — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework Reference — External STOMP Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework API — SimpUserRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/SimpUserRegistry.html)
- [Spring Framework API — MultiServerUserRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/MultiServerUserRegistry.html)
- [Spring Framework API — UserRegistryMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/UserRegistryMessageHandler.html)
- [Spring Framework API — DefaultUserDestinationResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/DefaultUserDestinationResolver.html)
- [Spring Framework API — DestinationUserNameProvider](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/DestinationUserNameProvider.html)
- [Spring Framework API — StompBrokerRelayRegistration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)