# In-Memory Simple Broker and Subscription Management

## Objectives

Spring Framework provides a built-in simple message broker for WebSocket/STOMP applications. The broker receives SUBSCRIBE requests, stores subscription information in memory, and broadcasts messages to connected clients with matching destinations.

After this lesson, you can:

- Configure the simple broker with destination prefixes such as /topic and /queue.
- Explain the lifecycle of SUBSCRIBE, UNSUBSCRIBE, and DISCONNECT.
- Understand how the broker stores subscriptions, finds matching subscribers, and sends MESSAGE frames.
- Use destination patterns, heartbeats, and selectors when appropriate.
- Monitor the session lifecycle using ApplicationContext events.
- Recognize limitations regarding storage, ACK, receipts, and clustering to choose the right broker.

## 1. What is the Simple Broker?

The simple broker is a built-in message handler in Spring Messaging. When an application enables a STOMP message broker, Spring can create a SimpleBrokerMessageHandler to handle message brokering without needing to install an external broker server.

The simple broker performs three main tasks:

1. Receives SUBSCRIBE frames from clients and registers subscriptions in memory.
2. Receives messages whose destinations belong to a prefix managed by the broker.
3. Finds subscriptions with matching destinations and sends a MESSAGE frame to each corresponding client.

For example, an application configures the broker prefixes /topic and /queue. Clients A and B both subscribe to /topic/news. When the application broadcasts a message to /topic/news, both A and B receive the message if their connections remain active.

The simple broker is suitable for development, testing, internal applications, or moderate-scale systems where message broker requirements are still straightforward. It is not a standalone message broker with durable storage, distributed queue management, or clustering capabilities.

## 2. Role of the Simple Broker in the STOMP Flow

WebSocket creates a bidirectional connection between the browser and the server. STOMP defines the message frames that travel over that connection, such as CONNECT, CONNECTED, SEND, SUBSCRIBE, UNSUBSCRIBE, MESSAGE, and DISCONNECT.

Spring organizes the processing flow using three main channels:

- clientInboundChannel: receives messages from WebSocket sessions.
- brokerChannel: passes messages from the application to the message broker.
- clientOutboundChannel: sends messages from the server back to WebSocket sessions.

With a typical configuration, destinations are divided into two groups:

| Group | Example | Handling Component |
| --- | --- | --- |
| Application destination | /app/orders.create | @MessageMapping method |
| Broker destination | /topic/orders, /queue/alerts | Simple broker |

Configuring the application prefix /app designates messages going into application logic. The /topic and /queue prefixes are handed over to the simple broker to process.

Flow of a broadcast message:

1. A client connects to the WebSocket endpoint, e.g., /ws, then sends STOMP CONNECT.
2. The server replies with CONNECTED after the STOMP session is established.
3. The client sends SUBSCRIBE with destination /topic/news and a subscription id.
4. The simple broker records the subscription associated with the current session.
5. The application or a controller sends a message to /topic/news.
6. The broker finds subscriptions matching the destination.
7. For each matching subscription, Spring creates a message to send back to the corresponding session via clientOutboundChannel.
8. The client receives the MESSAGE frame and processes the payload.

Important point: clients can subscribe to broker destinations without needing to call an @MessageMapping. Controllers only participate when the destination is routed to an application prefix or when the application actively invokes a message-sending API.

## 3. Configuring the Simple Broker

A basic configuration:

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

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
    }
}
~~~

Meaning:

- @EnableWebSocketMessageBroker enables the WebSocket/STOMP infrastructure with a message broker.
- addEndpoint("/ws") registers the HTTP handshake endpoint for clients to open WebSocket connections.
- setApplicationDestinationPrefixes("/app") reserves destinations starting with /app for controllers.
- enableSimpleBroker("/topic", "/queue") registers the simple broker to handle destinations starting with /topic or /queue.

Some destination examples:

| Destination | Common Purpose |
| --- | --- |
| /topic/news | Broadcast news to all matching subscribers |
| /topic/rooms/engineering | Broadcast within a room |
| /queue/notifications | Destination name commonly used for notifications |
| /app/orders.create | Send a request for the application to process |

Prefix names are routing conventions. In particular, in the simple broker, /queue does not automatically become a point-to-point queue. The broker still broadcasts messages to every subscription matching the destination. If A and B both subscribe to /queue/notifications, both can receive the same message.

You should not use the same prefix for application controllers and the broker unless intentional. When both components handle the same destination, messages may be processed in parallel with no guarantee of which component processes them first.

## 4. How Does the Broker Manage Subscriptions?

A STOMP SUBSCRIBE typically contains at least a destination and an id. The subscription id must be distinguishable within the scope of a single session. A client can register multiple subscriptions on the same connection, including multiple subscriptions to the same destination, as long as their ids differ.

Conceptually, the registry manages the following information:

- Session id: identifies the client's STOMP connection.
- Subscription id: identifies a subscription within the session.
- Destination: where the client wants to receive messages.
- Additional information: headers or selectors if configured.

Spring uses the SubscriptionRegistry abstraction to store and look up subscriptions. The default configuration uses DefaultSubscriptionRegistry. The registry stores state in the memory of the Spring process and uses a PathMatcher to match destinations.

For example, a session can register:

| Session | Subscription id | Destination |
| --- | --- | --- |
| session-A | sub-1 | /topic/news |
| session-A | sub-2 | /topic/orders |
| session-A | sub-3 | /topic/news |
| session-B | sub-1 | /topic/news |

When the broker broadcasts a message to /topic/news, all three subscriptions—sub-1, sub-3 of session-A, and sub-1 of session-B—match. Because session-A has two different subscriptions for the same destination, the client can receive one message for each of those subscriptions. If you only want one handler to receive the message, avoid unintentionally registering duplicate destinations.

### Subscription Lifecycle

| Action | STOMP Frame | Result on the Server |
| --- | --- | --- |
| Start connection | CONNECT | Creates a STOMP session after successful handshake and authentication |
| Subscribe to receive messages | SUBSCRIBE | Stores subscription id and destination in the registry |
| Cancel a subscription | UNSUBSCRIBE | Removes the subscription by id in the session |
| Close session | DISCONNECT or WebSocket close | Removes all subscriptions belonging to the session |

When a client calls UNSUBSCRIBE, the client must use the exact id of the subscription to cancel. When the connection is closed, Spring automatically removes the subscriptions attached to that session. A reconnecting client creates a new session and needs to re-register its subscriptions.

The simple broker does not durably persist subscriptions to recover after an application restart. It also does not retain messages for redelivery to offline clients. Therefore, subscriptions and message reception are only valid during the lifetime of the current connection.

## 5. Destination Matching and Wildcards

The simple broker uses a PathMatcher to compare a message's destination against the destination in a subscription. By default, Spring uses AntPathMatcher with a forward slash / as the separator.

Commonly used pattern characters:

| Pattern | Meaning | Example |
| --- | --- | --- |
| * | Matches characters within a single path segment | /topic/rooms/* |
| ** | Matches multiple path segments | /topic/** |
| ? | Matches a single character in a segment | /topic/room? |
| {name} | Path variable in a controller mapping | /app/rooms/{roomId} |

Examples:

- A /topic/rooms/* subscription can match /topic/rooms/engineering.
- A /topic/** subscription can match deeper destinations under /topic.
- Wildcard patterns should be used intentionally because an overly broad subscription can receive more messages than expected.

The {roomId} variable is typically used in @MessageMapping mappings and extracted with @DestinationVariable. When using patterns for broker subscriptions, the goal is matching destinations to distribute messages; do not confuse this mechanism with binding controller parameters.

### Using Dots as Separators

Some systems use destinations in the form event.order.created instead of /event/order/created. You can change the PathMatcher:

~~~java
import org.springframework.util.AntPathMatcher;

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setPathMatcher(new AntPathMatcher("."));
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

When changing the separator, use it consistently in both controller mappings and broker subscriptions. With the simple broker, the configured PathMatcher also affects how the broker compares message destinations against subscription patterns. With an external broker, destination rules also depend on the external broker.

## 6. Sending Messages to Subscriptions

The application can broadcast messages to the broker using SimpMessagingTemplate:

~~~java
package com.example.messaging;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class AnnouncementPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public AnnouncementPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(Announcement announcement) {
        messagingTemplate.convertAndSend("/topic/announcements", announcement);
    }
}
~~~

When convertAndSend is called, Spring converts the payload into a message and sends it through brokerChannel. The simple broker finds matching subscriptions and broadcasts the message to the clients.

You can broadcast from a controller, service, listener, or background task. No STOMP controller is required if the message is generated from another business event, such as an order being confirmed or a job status changing.

Messages are only sent to matching subscriptions that exist at the moment the broker processes the message. Clients that are not connected or have not yet subscribed will not receive the message later.

## 7. Unsubscribing from the Client

Example using the JavaScript library @stomp/stompjs:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  reconnectDelay: 5000
});

let newsSubscription;

client.onConnect = () => {
  newsSubscription = client.subscribe("/topic/news", (frame) => {
    const news = JSON.parse(frame.body);
    console.log(news.title);
  });
};

client.activate();

// When news updates are no longer needed:
newsSubscription?.unsubscribe();

// When closing the page or leaving the screen:
await client.deactivate();
~~~

client.subscribe returns a Subscription object. Calling unsubscribe() on that object sends the corresponding UNSUBSCRIBE frame. Calling deactivate() closes the client and terminates the connection; the server cleans up remaining subscriptions belonging to the session when the session ends.

With reconnects, the onConnect callback is invoked again when a new connection is established. Re-subscribe to the necessary destinations inside this callback. Do not assume that subscriptions from the old session still exist in the new session.

A common mistake is calling subscribe repeatedly every time a UI component renders without unsubscribing the old subscription. This creates duplicate subscriptions, causing a single message to be processed multiple times. Manage subscription handles according to the component or screen lifecycle.

## 8. Monitoring Session and Subscription Lifecycles

Spring publishes useful ApplicationContext events for tracking connections and subscriptions:

| Event | Timing |
| --- | --- |
| SessionConnectEvent | A new STOMP CONNECT is received |
| SessionConnectedEvent | The broker has sent CONNECTED; the STOMP session is considered established |
| SessionSubscribeEvent | A STOMP SUBSCRIBE is received |
| SessionUnsubscribeEvent | A STOMP UNSUBSCRIBE is received |
| SessionDisconnectEvent | The STOMP session ends |

Example logging listener:

~~~java
package com.example.messaging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;
import org.springframework.web.socket.messaging.SessionSubscribeEvent;
import org.springframework.web.socket.messaging.SessionUnsubscribeEvent;

@Component
public class StompSessionEvents {

    private static final Logger log =
            LoggerFactory.getLogger(StompSessionEvents.class);

    @EventListener
    public void onSubscribe(SessionSubscribeEvent event) {
        StompHeaderAccessor headers =
                StompHeaderAccessor.wrap(event.getMessage());

        log.info("SUBSCRIBE session={}, id={}, destination={}",
                headers.getSessionId(),
                headers.getSubscriptionId(),
                headers.getDestination());
    }

    @EventListener
    public void onUnsubscribe(SessionUnsubscribeEvent event) {
        StompHeaderAccessor headers =
                StompHeaderAccessor.wrap(event.getMessage());

        log.info("UNSUBSCRIBE session={}, id={}",
                headers.getSessionId(),
                headers.getSubscriptionId());
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        log.info("DISCONNECT session={}, user={}",
                event.getSessionId(),
                event.getUser());
    }
}
~~~

These events are useful for logging, counting connections, updating online status, or releasing business resources tied to a session. SessionDisconnectEvent is sometimes published multiple times for the same session, so cleanup logic must be idempotent: running repeatedly still yields the same result and does not cause errors.

SessionSubscribeEvent indicates that Spring has received the SUBSCRIBE frame. It is not a STOMP RECEIPT confirming that the broker has finished registering the subscription and is ready to broadcast messages. The simple broker does not support receipts. If a workflow needs to know precisely when brokerChannel finishes processing a subscription, use a server-side synchronization mechanism such as ExecutorChannelInterceptor.afterMessageHandled on brokerChannel.

You should not write another custom registry to replace the broker's internal registry solely to track subscriptions. If user state is needed, consider SimpUserRegistry or storing presence data in a separate business layer.

## 9. Heartbeats for Detecting Inactive Connections

WebSocket is a long-lived connection. Proxies, mobile networks, or clients can lose connectivity without explicitly closing the session. STOMP heartbeats help both sides detect connections that are no longer active.

The simple broker supports heartbeats when configured with a TaskScheduler. The example below uses the scheduler declared in Spring's built-in WebSocket configuration:

~~~java
package com.example.messaging;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class HeartbeatWebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    private TaskScheduler messageBrokerTaskScheduler;

    @Autowired
    public void setMessageBrokerTaskScheduler(
            @Lazy TaskScheduler taskScheduler) {
        this.messageBrokerTaskScheduler = taskScheduler;
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[] {10_000, 20_000})
                .setTaskScheduler(this.messageBrokerTaskScheduler);
    }
}
~~~

The two heartbeat values are in milliseconds:

- The first value is the interval at which the server sends heartbeats when there is no outgoing data.
- The second value is the interval at which the client should send heartbeats.
- A value of 0 means no heartbeat is required in the corresponding direction.

For example, 10,000 and 20,000 represent intervals of 10 seconds and 20 seconds before STOMP negotiates heartbeats with the client. This is not a guarantee that every message is sent at exact intervals; a heartbeat is a liveness check signal when no other data is flowing.

When using the TaskScheduler pre-declared in the built-in WebSocket configuration, Spring recommends injecting it via a setter with @Lazy to avoid circular dependencies between the WebSocket configuration and the application configuration. You can declare a custom TaskScheduler if the application needs control over the pool or scheduling.

The STOMP client must also configure compatible heartbeats. For example, with @stomp/stompjs:

~~~javascript
const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  heartbeatIncoming: 10000,
  heartbeatOutgoing: 10000,
  reconnectDelay: 5000
});
~~~

Heartbeats do not replace reconnect logic. When a connection is closed, the client needs to reconnect and re-subscribe to the required destinations.

## 10. Selectors for Filtering Messages by Header

In addition to matching destinations, DefaultSubscriptionRegistry can filter messages based on a Spring Expression Language (SpEL) expression in a subscription header. This feature is called a selector.

Since Spring Framework 6.1, selectors are disabled by default. They can be enabled by configuring the header name:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableSimpleBroker("/topic")
            .setSelectorHeaderName("selector");
}
~~~

When selectors are enabled, a client can send the selector header along with SUBSCRIBE. Conceptual example:

~~~javascript
const subscription = client.subscribe(
  "/topic/orders",
  (frame) => console.log(frame.body),
  { selector: "headers.region == 'north'" }
);
~~~

The expression is evaluated against the message headers, not the JSON payload. A message is only sent to the subscription if the destination matches and the selector evaluates to true.

Selectors are an additional filtering mechanism, not an authorization system. Do not use selectors as a substitute for user authentication or destination access control checks. Only enable this feature when there is a clear need and you can control the expressions sent by clients.

## 11. Message Processing Order

Message-processing channels may use thread pools. As a result, inbound or outbound messages can be processed across multiple threads, and the order observed by the client may differ from the order in which messages were sent to the channel.

If the application needs to preserve publish order per client session, configure:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setPreservePublishOrder(true);
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setApplicationDestinationPrefixes("/app");
}
~~~

If you need to preserve the order of messages received from the same client session, configure it on StompEndpointRegistry:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.setPreserveReceiveOrder(true);
    registry.addEndpoint("/ws");
}
~~~

Both options carry a performance cost. Only enable them when ordering is a genuine business requirement, such as state-change events that must be processed sequentially. If messages are independent, parallel processing usually delivers better throughput.

## 12. Limitations of the Simple Broker

The simple broker has several important limitations:

- **In-memory storage only:** subscriptions are lost when the session ends or the application restarts.
- **No message storage for offline clients:** clients must connect and subscribe before a message is broadcast.
- **Incomplete STOMP support:** the simple broker does not support ACK, RECEIPT, and certain other STOMP features.
- **No clustering:** each Spring instance keeps its own subscription registry. A message arriving at one instance is not automatically distributed to subscriptions on another instance.
- **Not a point-to-point queue:** the /queue prefix is only a destination prefix; the simple broker still broadcasts to all matching subscriptions.
- **No default ordering guarantee:** channels may process messages in parallel; enable preserve order when needed.

The simple broker is suitable when an application needs straightforward real-time broadcasting and connected clients can receive messages directly. If you need ACK, receipts, durable queues, competing consumers, message persistence, or multiple application instances, you should use a dedicated broker.

## 13. When to Switch to an External Broker?

Spring supports a STOMP broker relay to forward messages to an external broker such as RabbitMQ or ActiveMQ. Basic configuration:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableStompBrokerRelay("/topic", "/queue");
    registry.setApplicationDestinationPrefixes("/app");
}
~~~

The broker relay is a MessageHandler that opens TCP connections to an external broker, forwards Spring messages to the broker, and forwards messages received from the broker back to WebSocket sessions. The external broker is responsible for storage, routing, and subscription management according to its own capabilities.

| Requirement | Simple broker | External broker via relay |
| --- | --- | --- |
| No separate broker installation needed | Suitable | Requires an external broker |
| Broadcast to connected clients | Yes | Yes |
| Store subscriptions in memory | Yes | Managed by the broker |
| STOMP ACK/RECEIPT | Not fully supported | Depends on broker |
| Durable queues and message persistence | No | Depends on broker |
| Clustering and multi-node distribution | Not suitable | Supported via broker configuration |
| Operational simplicity | Easier | Requires operating additional infrastructure |

Switching to a broker relay does not automatically solve all reliability requirements. You must configure queues, exchanges, retention, access permissions, heartbeats, reconnects, and retry policies according to the specific broker.

When using a broker relay, Spring publishes a BrokerAvailabilityEvent when the connection status to the broker changes. Applications using SimpMessagingTemplate should monitor this status and still need to handle MessageDeliveryException when sending messages.

## 14. Security and Subscription Operations

The simple broker only routes messages by destination and subscription. It does not determine on its own which users are allowed to subscribe or publish to which destinations.

Key areas to control:

- **Session authentication:** authenticate users during the WebSocket handshake or integrate an appropriate token mechanism. Associate the authenticated Principal with the session.
- **SEND authorization:** verify whether the user is permitted to send messages to an application destination.
- **SUBSCRIBE authorization:** verify permission to read from a destination. A user must not be allowed to subscribe to a private topic simply by knowing the topic name.
- **Do not trust self-declared client data:** userId, role, or tenant in a payload does not prove identity. Use the security context and verify permissions on the server.
- **Subscription limits:** prevent a single session from registering an excessive number of destinations or overly broad wildcards.
- **Message size limits:** configure transport limits and validate payloads to reduce the risk of excessive memory consumption.
- **Lifecycle observability:** track session counts, subscriptions, abnormal disconnects, and message delivery errors; avoid logging tokens, cookies, or sensitive payloads.

For multi-tenant or multi-room applications, permissions must be checked at both moments: when a client sends a message and when a client subscribes to receive messages. Destination names should not be treated as secrets or as a security mechanism.

## 15. Testing the Simple Broker

An integration test should verify both the subscription lifecycle and the message flow:

1. Start the application with the WebSocket/STOMP endpoint and simple broker.
2. Connect two separate STOMP clients.
3. Have clients A and B subscribe to the same destination.
4. Have the application broadcast a message to that destination.
5. Verify that both A and B receive the payload.
6. Have client A send UNSUBSCRIBE.
7. Broadcast the next message and verify that A does not receive the new message while B still receives it.
8. Close session B and verify that B's subscription is no longer used.

You should also test the following scenarios:

- Two subscriptions with different ids on the same destination.
- A destination with no subscribers.
- Wildcards matching multiple destinations.
- A client reconnecting and re-registering subscriptions.
- Sudden WebSocket closure.
- Payloads with selector headers if the application enables selectors.
- A user lacking permission to SUBSCRIBE to a destination.

The simple broker does not support STOMP RECEIPT, so you cannot rely on RECEIPT to confirm that a subscription is ready. If an integration test requires exact synchronization, you can install an ExecutorChannelInterceptor on brokerChannel and use afterMessageHandled to know when the SUBSCRIBE message has finished processing. SessionSubscribeEvent only notifies that Spring received SUBSCRIBE; it does not replace confirmation of completed processing.

## 16. Common Pitfalls

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Client does not receive messages | Subscribed to wrong destination or prefix not configured | Compare the SUBSCRIBE destination against broker prefixes and the published destination. |
| Multiple callbacks run for one message | Client subscribed to the same destination multiple times | Check subscription ids and ensure unsubscribe is called when components are destroyed. |
| Both Client A and B receive messages on /queue | Simple broker broadcasts to all matching subscriptions | Remember that /queue in the simple broker does not have competing-consumer semantics. |
| Messages lost when client is offline | Simple broker does not store messages for replay | Use an external broker with persistence or store events in a database. |
| Subscriptions disappear after reconnect | A new connection creates a new session | Re-subscribe inside the onConnect callback. |
| Wildcard receives too many messages | Pattern is too broad | Narrow the pattern and check SUBSCRIBE permissions. |
| Heartbeat does not work | TaskScheduler not configured or client heartbeat incompatible | Check TaskScheduler, heartbeatValue, and client heartbeat settings. |
| Disconnect event handled multiple times | SessionDisconnectEvent can occur multiple times | Make cleanup logic idempotent. |
| Message order changes | Channel processes messages in parallel | Enable preserve publish/receive order when required by business logic. |
| Multiple instances do not see each other's subscriptions | Each simple broker only keeps state in the current instance | Use an external broker relay for multi-node distribution. |

## 17. Key Takeaways

- The simple broker is a built-in broker that stores subscriptions in memory and broadcasts to connected clients with matching destinations.
- SUBSCRIBE creates a subscription; UNSUBSCRIBE removes a subscription by id; when a session closes, Spring removes that session's subscriptions.
- DefaultSubscriptionRegistry manages subscriptions and uses a PathMatcher to match destinations.
- /topic and /queue are prefix conventions. With the simple broker, both broadcast to matching subscriptions.
- Heartbeats require a TaskScheduler; selectors are a header-based filtering feature and are disabled by default starting in Spring Framework 6.1.
- The simple broker does not fully support ACK/RECEIPT, does not store offline messages, and is not suitable for clustering.
- When you need durable queues, message persistence, competing consumers, or multi-node distribution, consider an external broker relay.

## References

- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework — Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework — Dots as Separators](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/destination-separator.html)
- [Spring Framework — Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)
- [DefaultSubscriptionRegistry Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/broker/DefaultSubscriptionRegistry.html)
- [SimpleBrokerMessageHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/broker/SimpleBrokerMessageHandler.html)
- [SimpleBrokerRegistration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/SimpleBrokerRegistration.html)

