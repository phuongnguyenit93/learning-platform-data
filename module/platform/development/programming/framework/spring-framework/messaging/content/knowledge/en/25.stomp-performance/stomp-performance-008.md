# SessionConnectEvent, SessionConnectedEvent, and Subscription Events in Spring STOMP

## Objective and Scope

Spring Framework publishes events in the ApplicationContext to notify of important milestones in the lifecycle of a STOMP session running over WebSocket or SockJS. These events help applications track connections, subscription states, user sessions, and disconnects.

Common events include:

- **SessionConnectEvent:** Spring has received STOMP CONNECT from a client. This signals the client is starting the connection process at the STOMP layer.
- **SessionConnectedEvent:** the broker has replied with STOMP CONNECTED. At this point, the STOMP session is considered successfully established.
- **SessionSubscribeEvent:** Spring has received a STOMP SUBSCRIBE.
- **SessionUnsubscribeEvent:** Spring has received a STOMP UNSUBSCRIBE.
- **SessionDisconnectEvent:** the STOMP session has ended.

These events must be distinguished from WebSocket handshake events. WebSocket may already be upgraded successfully while the client has not yet sent STOMP CONNECT. Conversely, receiving CONNECT does not prove the broker accepted and sent CONNECTED. These two milestones have different meanings when tracking state and measuring performance.

The content focuses on Spring Framework STOMP over WebSocket/SockJS, ApplicationContext events, how to read message headers, and how to manage session/subscription state. These events are lifecycle notifications; they do not replace ChannelInterceptor for handling individual messages or authorization mechanisms.

## 1. Lifecycle of a STOMP Session

A client typically goes through the following steps:

1. Open an HTTP/WebSocket or SockJS connection to the Spring application.
2. Send STOMP CONNECT.
3. Spring publishes **SessionConnectEvent** upon receiving CONNECT.
4. The broker or simple broker replies with STOMP CONNECTED.
5. Spring publishes **SessionConnectedEvent**.
6. Client sends SUBSCRIBE; Spring publishes **SessionSubscribeEvent**.
7. Client may send UNSUBSCRIBE; Spring publishes **SessionUnsubscribeEvent**.
8. When the client sends DISCONNECT or the transport closes, Spring publishes **SessionDisconnectEvent**.

~~~mermaid
sequenceDiagram
    participant Client
    participant Spring as Spring WebSocket/STOMP
    participant Broker as Simple broker / relay
    participant Listener as Application event listener
    Client->>Spring: WebSocket handshake
    Client->>Spring: STOMP CONNECT
    Spring->>Listener: SessionConnectEvent
    Spring->>Broker: CONNECT
    Broker-->>Spring: CONNECTED
    Spring->>Listener: SessionConnectedEvent
    Spring-->>Client: CONNECTED
    Client->>Spring: SUBSCRIBE
    Spring->>Listener: SessionSubscribeEvent
    Spring->>Broker: SUBSCRIBE
    Client->>Spring: UNSUBSCRIBE
    Spring->>Listener: SessionUnsubscribeEvent
    Spring->>Broker: UNSUBSCRIBE
    Client->>Spring: DISCONNECT / transport close
    Spring->>Listener: SessionDisconnectEvent
~~~

The diagram illustrates the conceptual order. Exact event emission timing may depend on the message channels and broker in use; do not rely on listeners to control the handshake or block messages.

## 2. SessionConnectEvent and SessionConnectedEvent

### 2.1. SessionConnectEvent: CONNECT Request Received

**SessionConnectEvent** is published when Spring receives a STOMP CONNECT frame from a client. The event marks an attempt to start a STOMP session, not the moment the WebSocket handshake just completed.

The event contains the message representing CONNECT. From the message you can read:

- Session ID assigned by Spring to the WebSocket session.
- Principal if already present from the HTTP handshake or set earlier.
- Native STOMP headers sent by the client.
- Other message header information for tracing.

This is an appropriate milestone to record a connection attempt, count how many times clients begin STOMP handshakes, or log safe audit metadata. It does not yet prove the broker responded with CONNECTED.

### 2.2. SessionConnectedEvent: STOMP Session Established

**SessionConnectedEvent** is published shortly after SessionConnectEvent when the broker sends a STOMP CONNECTED frame in reply to CONNECT. At this point, the STOMP session can be considered fully established.

This is the appropriate milestone to:

- Mark the session as ACTIVE.
- Start tracking connected session duration.
- Update user presence.
- Allow tasks that depend on a ready STOMP session.
- Record the duration from CONNECT to CONNECTED to measure handshake latency.

If you only count received CONNECT frames, the application may count incomplete connection attempts. To measure successful STOMP sessions, rely on SessionConnectedEvent.

### 2.3. Comparison Table

| Criterion | SessionConnectEvent | SessionConnectedEvent |
|---|---|---|
| Timing | Spring receives CONNECT | Broker returns CONNECTED |
| Meaning | Client initiates STOMP handshake | STOMP session is established |
| Guarantees broker accepted CONNECT? | Not yet | Yes, CONNECTED response received |
| Useful data | Session ID, user, CONNECT headers | Session ID, user, CONNECTED response |
| Use case | Audit attempts, track pending connections | Mark ACTIVE, measure handshake duration |
| Synonymous with WebSocket handshake? | No | No; this is state at the STOMP layer |

## 3. SessionSubscribeEvent and SessionUnsubscribeEvent

### 3.1. SessionSubscribeEvent

**SessionSubscribeEvent** is published when Spring receives a STOMP SUBSCRIBE. The event message contains useful headers such as:

- Client's session ID.
- Session Principal.
- Destination the client wants to subscribe to.
- Subscription ID provided by the client.
- Other relevant STOMP headers.

Example client subscribe:

~~~javascript
client.subscribe("/topic/orders", (message) => {
    console.log(message.body);
}, {
    id: "orders-subscription"
});
~~~

The corresponding event can be used to record that the session requested subscription to destination /topic/orders with subscription ID orders-subscription.

Do not treat this event as proof that the client has already received messages or that the subscription was confirmed by the broker. It is a notification that Spring received SUBSCRIBE. With a broker relay, if protocol-level confirmation is needed, use the STOMP RECEIPT mechanism appropriate to the broker/client and check the receipt frame.

### 3.2. SessionUnsubscribeEvent

**SessionUnsubscribeEvent** is published when Spring receives STOMP UNSUBSCRIBE. The application can use it to update subscription state or release resources associated with the subscription ID.

Example:

~~~javascript
const subscription = client.subscribe("/topic/orders", handler, {
    id: "orders-subscription"
});

// When data is no longer needed:
subscription.unsubscribe();
~~~

Unsubscribing from one subscription does not mean the WebSocket/STOMP session ends. A client can unsubscribe from one destination and continue subscribing to other destinations within the same session.

### 3.3. Subscription ID and Destination

One session can have multiple subscriptions, including multiple subscriptions to the same destination with different IDs. When tracking, store the pair of session ID and subscription ID; destination is useful for statistics and auditing.

Do not use destination alone as a key because the same destination can be subscribed to multiple times by the same or multiple sessions. Nor should you assume subscription IDs are globally unique; they are chosen by the client and usually only have meaning within the corresponding session.

## 4. SessionDisconnectEvent and Safe Duplicate Handling

**SessionDisconnectEvent** is published when a STOMP session ends. DISCONNECT may come from the client or be generated by Spring when the WebSocket session closes.

Spring warns that in some circumstances, a single session can publish SessionDisconnectEvent more than once. Therefore, listeners must handle it idempotently: receiving a duplicate event must not delete resources twice, deduct credits twice, or record two independent offline transitions.

Rules to apply:

- Use session ID to identify the exact session needing cleanup.
- Remove state only if the session still exists in the application's registry.
- Use a remove-if-present operation or a state flag so cleanup takes effect only once.
- Do not mark a user offline immediately when one session disconnects if the user has other active sessions.
- Close session-related resources such as subscription metadata, listeners, or locks according to defined policy.
- Do not treat a disconnect event as definitive proof that the user logged out of the entire application.

For example, a user opens two tabs with two WebSocket sessions. When the first tab closes, the user still has the second tab. User presence should only transition to offline when no sessions remain for that user.

## 5. Reading Data from Events

These events inherit from **AbstractSubProtocolEvent**, providing message and user. You can use **StompHeaderAccessor** to read STOMP-specific headers.

Commonly used methods:

| Method | Meaning |
|---|---|
| getMessage() | Original message attached to the event |
| getUser() | Session Principal if present |
| getSessionId() | Session ID in message headers |
| getDestination() | Destination of SUBSCRIBE/UNSUBSCRIBE or related message |
| getSubscriptionId() | Subscription ID |
| getCommand() | STOMP command |
| getSessionAttributes() | Attributes attached to the WebSocket session if present |

Example listener:

~~~java
package com.example.messaging.events;

import java.security.Principal;
import java.util.logging.Logger;

import org.springframework.context.event.EventListener;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectEvent;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;
import org.springframework.web.socket.messaging.SessionSubscribeEvent;
import org.springframework.web.socket.messaging.SessionUnsubscribeEvent;

@Component
public class StompLifecycleEventListener {

    private static final Logger LOGGER =
            Logger.getLogger(StompLifecycleEventListener.class.getName());

    @EventListener
    public void onConnect(SessionConnectEvent event) {
        logEvent("CONNECT_RECEIVED", event.getMessage(), event.getUser());
    }

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        logEvent("CONNECTED", event.getMessage(), event.getUser());
    }

    @EventListener
    public void onSubscribe(SessionSubscribeEvent event) {
        logEvent("SUBSCRIBE", event.getMessage(), event.getUser());
    }

    @EventListener
    public void onUnsubscribe(SessionUnsubscribeEvent event) {
        logEvent("UNSUBSCRIBE", event.getMessage(), event.getUser());
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        logEvent("DISCONNECT", event.getMessage(), event.getUser());
    }

    private void logEvent(String type, Message<?> message, Principal user) {
        StompHeaderAccessor headers = StompHeaderAccessor.wrap(message);

        String sessionId = headers.getSessionId();
        String destination = headers.getDestination();
        String subscriptionId = headers.getSubscriptionId();
        String username = user == null ? "anonymous" : user.getName();

        LOGGER.info(() -> type
                + " session=" + sessionId
                + " user=" + username
                + " destination=" + destination
                + " subscriptionId=" + subscriptionId);
    }
}
~~~

The example uses java.util.logging for readability and zero logging facade dependencies. In a real application, you can use SLF4J and structured logging. Consider personal data in logs; use internal user IDs or pseudonymized values if real usernames are not needed.

Do not log the entire native headers map or raw messages. CONNECT may carry bearer tokens, CSRF tokens, or authentication data depending on the application. Log only fields needed for operations and strip secrets before logging.

## 6. Managing Session and Subscription State

### 6.1. Using Events to Maintain an Application Registry

A simple registry can store sessions and subscription sets by session ID. The following example illustrates the update operations; production applications must define appropriate storage scope, synchronization, and lifetime.

~~~java
package com.example.messaging.events;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;
import org.springframework.web.socket.messaging.SessionSubscribeEvent;
import org.springframework.web.socket.messaging.SessionUnsubscribeEvent;

@Component
public class SubscriptionRegistry {

    private final ConcurrentMap<String, Set<String>> subscriptions =
            new ConcurrentHashMap<>();

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        String sessionId = StompHeaderAccessor.wrap(event.getMessage())
                .getSessionId();

        if (sessionId != null) {
            subscriptions.putIfAbsent(
                    sessionId, ConcurrentHashMap.newKeySet());
        }
    }

    @EventListener
    public void onSubscribe(SessionSubscribeEvent event) {
        StompHeaderAccessor headers =
                StompHeaderAccessor.wrap(event.getMessage());

        String sessionId = headers.getSessionId();
        String subscriptionId = headers.getSubscriptionId();

        if (sessionId != null && subscriptionId != null) {
            subscriptions
                    .computeIfAbsent(
                            sessionId, key -> ConcurrentHashMap.newKeySet())
                    .add(subscriptionId);
        }
    }

    @EventListener
    public void onUnsubscribe(SessionUnsubscribeEvent event) {
        StompHeaderAccessor headers =
                StompHeaderAccessor.wrap(event.getMessage());

        String sessionId = headers.getSessionId();
        String subscriptionId = headers.getSubscriptionId();

        if (sessionId == null || subscriptionId == null) {
            return;
        }

        Set<String> ids = subscriptions.get(sessionId);
        if (ids != null) {
            ids.remove(subscriptionId);
            if (ids.isEmpty()) {
                subscriptions.remove(sessionId, ids);
            }
        }
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        String sessionId = StompHeaderAccessor.wrap(event.getMessage())
                .getSessionId();

        if (sessionId != null) {
            // remove() only returns data on the first call; duplicate events do not cause duplicate cleanup.
            subscriptions.remove(sessionId);
        }
    }

    public int subscriptionCount(String sessionId) {
        Set<String> ids = subscriptions.get(sessionId);
        return ids == null ? 0 : ids.size();
    }
}
~~~

The registry above is only an in-memory illustration for a single application instance. When deploying multiple instances, local session data is not automatically shared across instances. Use a distributed mechanism or an appropriate **SimpUserRegistry**/user registry if cluster-wide state aggregation is needed.

### 6.2. Presence of a User with Multiple Sessions

A user can connect from multiple tabs, windows, devices, or browsers. Therefore, a presence model should map a user to a set of session IDs:

~~~text
alice -> {session-1, session-2}
bob   -> {session-3}
~~~

When session-1 disconnects, Alice is still online because session-2 remains active. Only when Alice's last session disconnects can the application mark Alice offline.

In real implementations, concurrency must be handled: two sessions may connect/disconnect almost simultaneously. Use atomic operations, appropriate locks, or storage with required consistency to avoid incorrect presence state.

### 6.3. SimpUserRegistry

Spring provides **SimpUserRegistry** to query users, sessions, and subscriptions tracked by the messaging infrastructure. If you only need to inspect current state, consider using the built-in registry instead of rebuilding all data from ApplicationContext events.

Event listeners remain useful when auditing, metrics, business resource cleanup, or syncing state to external systems is required. The built-in registry and event listeners serve complementary needs.

## 7. How Do Event Listeners and ChannelInterceptor Differ?

ApplicationContext events notify of STOMP lifecycle milestones. They are not published for every message a client sends. If you need to observe or intercept individual frames/messages, use **ChannelInterceptor**.

| Mechanism | Scope | Use Case |
|---|---|---|
| SessionConnectEvent | CONNECT received | Tracking STOMP handshake initiation |
| SessionConnectedEvent | CONNECTED response received | Marking session ready |
| SessionSubscribeEvent | SUBSCRIBE received | Tracking destination subscriptions |
| SessionUnsubscribeEvent | UNSUBSCRIBE received | Tracking subscription cancellations |
| SessionDisconnectEvent | Session ended | Cleanup and updating presence |
| ChannelInterceptor | Every message passing through a channel | Authentication, authorization, validation, tracing, metrics |

Example registering an inbound interceptor:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    private final ChannelInterceptor auditInterceptor;

    public WebSocketConfiguration(ChannelInterceptor auditInterceptor) {
        this.auditInterceptor = auditInterceptor;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(auditInterceptor);
    }
}
~~~

The interceptor can use **StompHeaderAccessor** to read command, destination, session ID, and user. It can inspect, reject, or enrich information before the message proceeds through the channel.

Do not use event listeners to block unauthorized SUBSCRIBE requests after the event has already been published. Authorization must be performed in the inbound message processing chain before the message is accepted.

## 8. Monitoring Broker Availability Separately from Session Events

**BrokerAvailabilityEvent** differs from per-session events. It indicates whether the broker relay's system connection is available. When an external broker restarts, the relay may automatically reconnect the system connection and publish an event when status changes.

This does not mean all client connections have been restored. TCP connections on behalf of clients have their own lifecycles; clients must reconnect STOMP/WebSocket themselves when disconnected.

Services sending messages via **SimpMessagingTemplate** should monitor broker availability and still handle **MessageDeliveryException** when sending. Do not take SessionConnectedEvent counts as an indicator that the broker system connection is ready for all server-to-broker operations.

## 9. Performance Measurement and Operations

Events allow building meaningful metrics:

- **CONNECT attempts:** count of SessionConnectEvent.
- **STOMP sessions established:** count of SessionConnectedEvent.
- **Handshake latency:** duration from SessionConnectEvent to SessionConnectedEvent per session ID.
- **Subscription activity:** counts of SessionSubscribeEvent and SessionUnsubscribeEvent.
- **Active sessions:** count of successfully established sessions minus disconnected sessions, handling duplicate events.
- **Session duration:** duration from CONNECTED to DISCONNECT.
- **Disconnect rate:** count of unique SessionDisconnectEvent divided by established sessions.

Do not use received CONNECT count as the number of successful connections. A client may open a WebSocket without sending CONNECT, or send CONNECT without the broker returning CONNECTED.

Do not treat every SessionDisconnectEvent as a new disconnect because Spring may publish duplicate events. For metrics, count unique session IDs or increment the counter only when the registry actually transitions state from active to removed.

### 9.1. Keep Listeners Lightweight

ApplicationContext listeners typically run synchronously on the event-publishing thread unless the application configures async event handling. Do not perform slow database queries, external API calls, or heavy report processing directly inside a listener, as doing so can slow down the messaging flow.

If heavy processing is needed, capture minimal event data and offload the task to an appropriate executor/queue. When switching to async, note that event ordering may no longer be guaranteed as in sequential processing; session state updates should use idempotent operations with concurrency control.

### 9.2. Do Not Store Secrets from Events

CONNECT events may contain custom headers sent by clients. These headers can be access tokens, CSRF tokens, or identifying data. Extract only session ID, Principal, destination, subscription ID, and necessary metadata. Do not log raw messages/header maps.

## 10. Common Errors and How to Handle Them

| Issue | Cause | Resolution |
|---|---|---|
| WebSocket opened but no SessionConnectedEvent | Client has not sent CONNECT or broker has not replied CONNECTED | Track handshake and STOMP CONNECT separately; check broker |
| SessionConnectEvent fired but client not ready | Event only marks CONNECT received | Wait for SessionConnectedEvent to mark STOMP session active |
| SessionSubscribeEvent does not mean messages reached client | Event only indicates SUBSCRIBE was received | Check broker receipt and actual message flow |
| User presence goes offline too early | User has multiple sessions but application counts only per user | Track a set of session IDs per user |
| Resources cleaned up twice | SessionDisconnectEvent can fire multiple times | Use remove-if-present and idempotent cleanup |
| Session metrics go negative or become wrong | Duplicate events, race conditions, or failed CONNECTs | Update state strictly by session ID and valid state transitions |
| Listener slows down message processing | Synchronous listener calls slow work | Keep listeners short, offload heavy work to executor/queue |
| Subscriptions not found after reconnect | New session has a new session ID; old subscriptions belonged to old session | Client re-subscribes after reconnect and registry updates for the new session |

## 11. Testing Checklist

1. Connect WebSocket without sending STOMP CONNECT: do not count as an established STOMP session.
2. Send CONNECT successfully: observe SessionConnectEvent followed by SessionConnectedEvent.
3. Reject or fail CONNECT: do not mark session active if CONNECTED was not received.
4. Subscribe to multiple destinations: each SUBSCRIBE is observed with the correct session ID and subscription ID.
5. Unsubscribe one subscription: session stays active and other subscriptions remain.
6. Normal disconnect: clean up all session subscription metadata.
7. Unexpected WebSocket close: cleanup still happens when Spring publishes disconnect event.
8. Send disconnect or close transport along different paths: duplicate events do not corrupt cleanup/metrics.
9. One user opens two sessions: disconnecting one session does not mark the user offline while the other session is active.
10. Broker relay drops and recovers: test BrokerAvailabilityEvent separately and verify client reconnects.
11. Generate load with many sessions/subscriptions: measure listener duration and ensure listeners do not bottleneck inbound/outbound channels.

## 12. Design Principles

1. **Distinguish WebSocket and STOMP lifecycles.** Successful handshake does not mean STOMP CONNECTED.
2. **Use the right event for the right milestone.** SessionConnectEvent is CONNECT received; SessionConnectedEvent is CONNECTED replied.
3. **Track by session ID.** One user can have multiple sessions and each session can have multiple subscriptions.
4. **Idempotent cleanup.** SessionDisconnectEvent may be published multiple times.
5. **Do not turn events into an authorization mechanism.** Use ChannelInterceptor or Spring Security to check each message.
6. **Keep listeners lightweight.** Offload heavy work to an executor/queue and control ordering if needed.
7. **Do not log secrets.** Event messages can contain client-sent native headers.
8. **Measure the right states.** Distinguish CONNECT attempt, STOMP session established, subscription request, and broker availability.

## 13. References

- [Spring Framework – Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [SessionConnectEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/SessionConnectEvent.html)
- [SessionConnectedEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/SessionConnectedEvent.html)
- [SessionSubscribeEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/SessionSubscribeEvent.html)
- [SessionUnsubscribeEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/SessionUnsubscribeEvent.html)
- [SessionDisconnectEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/SessionDisconnectEvent.html)
- [Spring Framework – Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html)
