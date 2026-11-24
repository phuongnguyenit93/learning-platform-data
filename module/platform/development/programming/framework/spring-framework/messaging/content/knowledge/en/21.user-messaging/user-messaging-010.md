# Handling Unresolved User Destinations in a Cluster

## Objectives

In a Spring STOMP application running across multiple application instances, a WebSocket session is directly connected to only one instance at a time. For example, user `alice` connects to node B, yet a business task processed on node A calls `convertAndSendToUser("alice", ...)`.

If node A only looks up its local session list, it may fail to find `alice`. Spring refers to this situation as an unresolved user destination. Spring supports two coordinated mechanisms via a broker relay to handle it:

- **User registry broadcast** shares user/session information between application instances.
- **Unresolved user destination broadcast** forwards unresolved messages so other instances can attempt resolution.

These two mechanisms enable sending messages to sessions connected on another node. They do not create a durable mailbox for offline users.

## 1. Why can a user destination be unresolved?

Clients typically subscribe to a logical destination:

~~~javascript
client.subscribe('/user/queue/notifications', (frame) => {
  const notification = JSON.parse(frame.body);
  console.log(notification.message);
});
~~~

The `/user` prefix is handled by Spring's `UserDestinationMessageHandler`. Spring translates the logical destination into a physical destination private to the session, for example:

~~~text
/user/queue/notifications
        |
        | UserDestinationMessageHandler
        v
/queue/notifications-user123
~~~

The physical destination name is an internal detail. The client only needs to subscribe to the logical destination `/user/queue/notifications`; do not manually create or guess session suffixes.

On the sending side, a service can use:

~~~java
messagingTemplate.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        payload
);
~~~

Spring looks up the user in the application's `SimpUserRegistry`. In a single instance, that registry typically contains users/sessions connected to that instance itself.

In a multi-node cluster, the situation can look like this:

- Node A receives a business event and needs to send to `alice`.
- Node B is holding `alice`'s WebSocket session.
- Node A's local registry does not yet know about the session on node B.
- Node A cannot produce the corresponding physical destination solely from its local registry.

Without configuring registry sharing or unresolved message broadcasting, the message may never reach the session on node B.

## 2. Two broadcast mechanisms solve two different problems

Spring provides two settings on `StompBrokerRelayRegistration`, the object returned by `MessageBrokerRegistry.enableStompBrokerRelay(...)`.

| Mechanism | Configuration | Purpose |
|---|---|---|
| Share user registry | `setUserRegistryBroadcast(...)` | Broadcast local registry information and receive registry updates from other nodes |
| Forward unresolved messages | `setUserDestinationBroadcast(...)` | Broadcast unresolved messages so other nodes have a chance to find matching sessions |

**User registry broadcast** lets each node learn about users/sessions connected on other nodes. Spring combines local and remote registries through `MultiServerUserRegistry`, giving the user destination resolver cluster-wide information.

**Unresolved destination broadcast** is a fallback path for messages that the current node cannot resolve. The message is sent to a shared broker destination; other nodes receive the message and get a chance to process it using their own local registries.

Both broadcast destinations are internal channels between application instances. They need to be distributed by the broker relay to all nodes participating in the cluster.

## 3. Configuring the broker relay for a cluster

Spring's built-in simple broker stores subscriptions in the memory of a single application instance. It is suitable for development or simple deployments, but does not provide user registry sharing or unresolved destination broadcasting across multiple instances.

To use these broadcast mechanisms, configure a STOMP broker relay pointing to an external message broker. Example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class ClusterWebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setUserDestinationBroadcast(
                        "/topic/internal/unresolved-user-destination")
                .setUserRegistryBroadcast(
                        "/topic/internal/user-registry");
    }
}
~~~

In this example:

- `/topic` and `/queue` are the broker destination prefixes handled by the relay.
- `/topic/internal/unresolved-user-destination` is the channel for forwarding unresolved messages.
- `/topic/internal/user-registry` is the channel for sharing the registry.
- Both internal destinations must be identical across all application instances in the same cluster.

The example focuses on the broadcast configuration. In a real environment, also configure the relay host, port, and credentials according to the message broker in use. Do not place broker passwords directly in source code; load credentials from secure configuration or environment variables.

The broadcast destinations must be supported by the broker in publish/subscribe mode so messages from one node are distributed to the remaining nodes. Merely pointing instances at independent brokers that do not share the same routing system does not form a messaging cluster capable of cross-node user destination routing.

## 4. Processing flow when the user is connected on another node

Suppose a cluster has node A and node B both connected to a STOMP broker:

~~~text
                  Shared STOMP broker
                 /                   \
          Node A                       Node B
   (publishing service)         (holds alice's session)
           |                             |
           |                             | WebSocket client
           |                             | SUBSCRIBE /user/queue/notifications
           |                             |
           +---- user registry broadcast +
           |
           +---- unresolved destination -> cluster nodes
~~~

General flow:

1. `alice`'s client connects over WebSocket to node B and subscribes to `/user/queue/notifications`.
2. Node B records the user/session in its local registry.
3. Node B broadcasts registry info over the destination configured via `setUserRegistryBroadcast`. Other nodes receive the info and can update the composite registry.
4. A service on node A calls `convertAndSendToUser("alice", "/queue/notifications", payload)`.
5. Spring looks up `alice`'s session using the available registry. When a remote session is found, the message is translated into the corresponding physical destination and sent through the broker.
6. If node A still cannot resolve the user destination, `setUserDestinationBroadcast` allows broadcasting the unresolved message so other nodes can attempt to handle it.
7. The node holding the matching session can resolve the message using its local registry and send it to the physical destination. The broker delivers the message to the subscribed WebSocket session.

Registry broadcast gives the sending node extra information about remote users. Unresolved broadcast gives the session-holding node a chance to handle the message when the sending node cannot find the target. These two mechanisms complement each other.

## 5. Sending to a user from a service

Business services still send using `SimpMessagingTemplate`. There is no need to manually pick the node holding the session or construct physical destinations:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String username, NotificationPayload payload) {
        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                payload
        );
    }
}
~~~

The client subscribes to the logical destination:

~~~javascript
client.subscribe('/user/queue/notifications', (frame) => {
  const payload = JSON.parse(frame.body);
  renderNotification(payload);
});
~~~

The user name passed to `convertAndSendToUser` must match the identity that Spring attaches to the WebSocket session, usually `Principal.getName()`. All nodes must use the same authentication and identity-mapping rules. If one node uses email while another uses username, the registry may exist yet name-based lookup will still fail.

By default, if a user has multiple sessions subscribed to the same destination, Spring can send to all matching sessions, such as multiple browser tabs logged into the same account.

## 6. Comparing configuration with the simple broker

The following configuration enables only an in-memory broker per instance:

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

When running two independent instances, each simple broker has its own subscription list. One node does not automatically know about sessions belonging to the other node. The configuration above does not provide multi-server user registry broadcast or unresolved destination broadcast.

To handle user destinations across nodes, use a broker relay and configure the broadcast destinations on the object returned by `enableStompBrokerRelay`:

~~~java
registry.enableStompBrokerRelay("/topic", "/queue")
        .setUserDestinationBroadcast(
                "/topic/internal/unresolved-user-destination")
        .setUserRegistryBroadcast(
                "/topic/internal/user-registry");
~~~

You cannot simply rename the `/topic` prefix or enable sticky sessions on a load balancer to replace this mechanism. Sticky sessions keep a client's requests/connections going to the same node, yet they do not transfer a message published by another node to the node holding the WebSocket session.

## 7. Requirements on the message broker and cluster

For broadcasts to work, check the following conditions:

- All application instances use the same broker or a broker system with interconnected routing.
- All instances use the same destinations for user registry broadcast and unresolved destination broadcast.
- The broadcast destinations fall within the destination scope handled by the broker relay.
- The broker supports publish/subscribe distribution to all nodes subscribed to the internal destinations.
- Each instance's relay system connection has permission to subscribe and publish to the internal destinations.
- User names in `Principal` are consistent across instances.
- Clients subscribe to the logical `/user/...` destination, not to physical destinations generated by Spring.
- Security rules prevent clients from arbitrarily reading or writing to the internal destinations.

`userRegistryBroadcast` carries information about the node's users/sessions. `userDestinationBroadcast` can carry the payload of messages to be forwarded. Restrict access to these destinations using broker ACLs and application authorization rules. Only appropriate server connections should be permitted to use internal channels.

## 8. When the user is genuinely offline

Unresolved destination broadcast only gives other nodes a chance to find an existing active session. If no node holds a session for the user, there will be no WebSocket target to deliver the message to.

These broadcast mechanisms are not an offline notification storage queue. If business logic requires users logging back in to still see past notifications:

1. Persist the notification to a database or a durable store.
2. Record the recipient user, content, creation timestamp, and read status.
3. Use `convertAndSendToUser` to notify online sessions in realtime.
4. When the client reconnects, load unread notifications via an API.
5. Update the read status through a separate business action.

If you need to ensure a business event is not lost between database commit and publishing, consider a Transactional Outbox or an equivalent replay mechanism. Broker relay and user destination broadcast do not by themselves provide exactly-once guarantees for the entire business flow.

## 9. Testing multi-node configuration

A unit test merely verifying that a service calls `convertAndSendToUser` does not prove cross-node routing works. An integration test with at least two application instances and a shared broker is required.

Test scenario:

1. Start the shared STOMP broker.
2. Start node A and node B with the same relay configuration and both broadcast destinations.
3. Connect a STOMP client to node B as user `alice`.
4. Wait for CONNECT to succeed and subscribe to `/user/queue/notifications`.
5. Wait for the registry broadcast to be processed.
6. Invoke the service on node A to send a notification to `alice`.
7. Verify that the client connected via node B receives the exact payload.
8. Try sending when `alice` has no remaining sessions on any node and confirm the application does not treat broadcast as offline notification storage.

You should also run a case where node B has just started or the registry has not yet updated to test unresolved destination broadcast. Check logs and broker subscriptions to confirm that system connections subscribed to the internal destinations properly.

## 10. Troubleshooting common errors

| Symptom | Possible cause | What to check |
|---|---|---|
| Sent from node A but client on node B does not receive | Nodes use different brokers or broker does not distribute topics across them | Check relay host, virtual host, broker cluster, and subscriptions |
| User has a session but sending node reports unresolved | Registry broadcast not enabled, not yet updated, or user name mismatch | Check `setUserRegistryBroadcast`, composite registry, and `Principal.getName()` |
| Unresolved message does not reach other nodes | `setUserDestinationBroadcast` not configured or broker ACL blocks destination | Check destination and publish/subscribe permissions of system connections |
| Configured broadcast but still running simple broker so it does not work | Simple broker is an in-memory per-instance broker | Switch to `enableStompBrokerRelay` and a shared broker |
| Client connected yet receives no notifications | Client subscribed to wrong destination or SUBSCRIBE has not succeeded | Use `/user/queue/notifications` and inspect STOMP frames |
| User receives multiple notifications across multiple tabs | User has multiple sessions subscribed to the destination | Check active sessions; this may be the default behavior |
| Offline user does not receive missed notifications | No session available to resolve the destination | Persist notifications durably and reload when client reconnects |
| Node does not receive registry broadcast | System connection lacks permissions or broker does not forward internal destinations | Check broker ACLs, relay logs, and node subscriptions |

## Key takeaways

- User destination `/user/...` is a logical destination; Spring translates it into a session-specific physical destination.
- A node's local registry does not inherently include sessions on other nodes.
- `setUserRegistryBroadcast` shares user/session information across nodes.
- `setUserDestinationBroadcast` forwards unresolved messages so other nodes can try handling them.
- Both settings are configured on the `StompBrokerRelayRegistration` returned by `enableStompBrokerRelay`.
- The simple broker does not provide these two multi-server broadcast mechanisms.
- Every node must share the same broker, internal destinations, and user identity rules.
- Broadcast only helps route to online sessions; supporting offline users requires durable notification storage.

## References

- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/user-destination.html)
- [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/enable.html)
- [StompBrokerRelayRegistration API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)
- [UserDestinationMessageHandler API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/simp/user/UserDestinationMessageHandler.html)
