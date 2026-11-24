# STOMP Message Distribution via External Broker in Multi-Server Deployments

## Objectives

When a Spring application runs on a single server, the built-in simple broker may be enough to manage subscriptions and broadcast messages. When the application is deployed as multiple instances behind a load balancer, each instance has its own memory and list of WebSocket sessions. If each instance uses the simple broker, a client connected to node A will not automatically receive messages that node B sends to its local broker.

The common solution is to use a **STOMP broker relay** so each Spring instance forwards messages to a shared external message broker. The broker handles subscription management and message distribution across connections arriving from multiple application instances.

This lesson explains the architecture, configuration, and operations of that model with Spring Framework 6.1. Specific broker examples use RabbitMQ for illustration; destination and queue semantics must be verified against the actual broker in use.

After this lesson, you will be able to:

- Distinguish between the simple broker and the external STOMP broker relay.
- Describe the message flow when running multiple Spring application servers.
- Configure `enableStompBrokerRelay` with destination prefixes, credentials, and heartbeats.
- Use `userRegistryBroadcast` and `userDestinationBroadcast` for user destinations across multiple nodes.
- Distinguish application destinations, broker destinations, and user destinations.
- Design authentication, authorization, queue lifecycle, and secure connections.
- Size connections, handle broker outages, and test cross-node message distribution.

## 1. The Problem with Running Multiple Application Servers

### 1.1. Simple Broker Holds Subscriptions in Each Node's Memory

Spring can enable the built-in broker with:

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

The simple broker manages subscriptions in the application instance's memory. Suppose there are two nodes:

~~~text
                    Load Balancer
                    /           \
                   v             v
             Spring Node A   Spring Node B
             Simple Broker   Simple Broker
             Client Alice    Client Bob
~~~

Alice connects via WebSocket to Node A. Bob connects to Node B. When Node A sends a message to `/topic/orders`, Node A's simple broker only knows the subscribers managed by Node A. It does not have Bob's subscription on Node B. The reverse is also true.

If every client always connected to the same node, this limitation might stay hidden. When scaling horizontally, rolling out deployments, or when clients reconnect to another node, each simple broker remains an isolated memory space.

Sticky sessions on the load balancer do not solve sharing subscriptions across nodes. They only keep a connection or group of requests pinned to one backend within the scope of the load balancer configuration.

### 1.2. External Broker as a Shared Distribution Point

With a broker relay, each Spring node still manages the WebSocket sessions of clients connected directly to that node. However, subscriptions and messages carrying broker prefixes are forwarded to a shared external broker:

~~~text
                         WebSocket clients
                       /                   \
                  Alice                     Bob
                    |                        |
                    v                        v
              Spring Node A            Spring Node B
              WebSocket session        WebSocket session
              STOMP relay              STOMP relay
                    |                        |
                    +-----------+------------+
                                |
                                v
                       External STOMP Broker
                       shared destinations
                                |
                    +-----------+------------+
                    |                        |
                    v                        v
              Relay Node A              Relay Node B
                    |                        |
                    v                        v
              Alice session             Bob session
~~~

When Alice publishes a message to a broker destination, Node A forwards the message to the broker. The broker finds matching subscriptions across the entire system and sends the message back to the corresponding relay connections. Node B receives the message from the broker and forwards it to Bob's WebSocket session.

As a result, application instances share a single message distribution system. The broker can be RabbitMQ, ActiveMQ, or another STOMP broker with suitable destination and feature support.

### 1.3. Broker Relay Does Not Replace the Application Server

Spring remains responsible for:

- Authenticating HTTP/WebSocket and attaching a `Principal` to the session.
- Routing messages sent to application destinations into `@MessageMapping` methods.
- Running validation, authorization, and business logic.
- Converting payloads, headers, and responses.
- Managing WebSocket sessions on the node holding the connection.
- Forwarding messages to the broker or receiving messages from the broker.

The external broker is responsible for:

- Managing STOMP subscriptions registered by relayed clients.
- Distributing messages to matching subscriptions.
- Enforcing queue/topic semantics according to the broker.
- Providing broker-supported features such as acknowledgements, receipts, persistence, or durable subscriptions.

The broker relay is a Spring `MessageHandler` that relays messages bidirectionally over TCP between Spring and the broker. It does not automatically share databases, HTTP sessions, caches, or business state across application nodes.

## 2. Simple Broker vs. STOMP Broker Relay

| Criterion | Simple Broker | STOMP Broker Relay |
|---|---|---|
| Where subscriptions are held | Memory of a single Spring application instance | External broker |
| Distribution across multiple Spring nodes | Not shared automatically | Possible via a shared broker |
| STOMP command support | Subset only | Depends on broker capabilities |
| `ACK`, `RECEIPT` | Not fully supported | Broker may support them |
| Persistence and durable subscriptions | Not the goal of the simple broker | Depends on broker and configuration |
| Operations | Fewer components | Must operate the broker, connections, and access control |
| Horizontal scaling | Not suitable as a broker cluster | Better suited when the broker is deployed with HA |

The simple broker is useful for development, demos, or simple applications. It is not a broker cluster and does not synchronize subscriptions across instances. Spring recommends using a broker relay when you need a full-featured broker and scalable message distribution.

Not all STOMP brokers support the same set of commands. `ACK`, `RECEIPT`, durable subscriptions, queue declarations, and specific destinations depend on the broker. Check the broker's documentation before designing the client protocol.

## 3. Destination Types in Spring STOMP

Distinguish three groups of destinations to avoid sending messages to the broker by mistake.

### 3.1. Application Destinations

Examples:

~~~text
/app/orders.create
/app/chat.send
~~~

Destinations prefixed with `/app` are routed by Spring to `@MessageMapping` methods. The `/app` prefix is stripped before Spring looks up the mapping.

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders.create")
    public OrderResult create(OrderCommand command) {
        return orderService.create(command);
    }
}
~~~

The client sends a STOMP `SEND` to `/app/orders.create`. The request is processed by the application instance holding the client's WebSocket session. The broker does not execute this controller method.

### 3.2. Broker Destinations

Common examples:

~~~text
/topic/orders
/queue/order-processing
~~~

Destinations prefixed with `/topic` or `/queue` are forwarded to the external broker when the relay is configured accordingly. The exact meaning of a destination is defined by the broker; STOMP does not require all brokers to interpret `/topic` and `/queue` identically.

Typically:

- A topic represents publish-subscribe: one message can be broadcast to many subscriptions.
- A queue represents point-to-point or work distribution: one message is typically delivered to one consumer in a group, depending on the broker.

Do not assume every subscriber to a queue receives a copy of the message. If broadcast is needed, choose destination and exchange semantics appropriate for the broker.

### 3.3. User Destinations

Example:

~~~text
/user/queue/notifications
~~~

Spring handles the `/user` prefix via `UserDestinationMessageHandler`. The logical destination is translated into a unique per-user/per-session destination so users do not collide on the same internal queue or subscription.

A client can subscribe:

~~~text
SUBSCRIBE
id:notifications-1
destination:/user/queue/notifications

^@
~~~

The server can send to a specific user via `SimpMessagingTemplate` or `@SendToUser`. User destinations are resolved by Spring before messages reach the broker; do not configure the broker to treat the `/user` prefix directly as a regular destination.

## 4. Configuring the Broker Relay

### 4.1. Declaring Endpoints and Broker Prefixes

A basic configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
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

        registry.enableStompBrokerRelay(
                "/topic",
                "/queue");
    }
}
~~~

Here:

- `/ws` is the HTTP endpoint where clients perform the WebSocket handshake.
- `/app` routes messages to `@MessageMapping`.
- `/topic` and `/queue` are relayed to the external broker.
- `/user` is Spring's default user destination prefix; it can be configured explicitly with `setUserDestinationPrefix` if desired.

Do not enable `enableSimpleBroker` with the same prefixes intended for the external relay in the same configuration. Clearly separate which prefixes belong to the application and which belong to the broker.

### 4.2. Configuring Host, Port, and Credentials

`StompBrokerRelayRegistration`, returned by `enableStompBrokerRelay`, lets you configure host, port, and credentials. Connection details should be loaded from the environment, a secret manager, or deployment configuration—never hard-code passcodes in source code.

The example below uses a record holding configuration loaded from a property source:

~~~java
public record StompRelayProperties(
        String host,
        int port,
        String clientLogin,
        String clientPasscode,
        String systemLogin,
        String systemPasscode,
        String virtualHost) {
}
~~~

The `StompRelayProperties` bean must be provided by the application configuration. Example using Spring `Environment`:

~~~java
@Configuration
class StompRelayPropertiesConfiguration {

    @Bean
    StompRelayProperties stompRelayProperties(
            Environment environment) {

        return new StompRelayProperties(
                environment.getRequiredProperty(
                        "messaging.stomp.relay.host"),
                environment.getRequiredProperty(
                        "messaging.stomp.relay.port", Integer.class),
                environment.getRequiredProperty(
                        "messaging.stomp.relay.client-login"),
                environment.getRequiredProperty(
                        "messaging.stomp.relay.client-passcode"),
                environment.getRequiredProperty(
                        "messaging.stomp.relay.system-login"),
                environment.getRequiredProperty(
                        "messaging.stomp.relay.system-passcode"),
                environment.getProperty(
                        "messaging.stomp.relay.virtual-host"));
    }
}
~~~

Relay configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    private final StompRelayProperties properties;

    public WebSocketConfiguration(
            StompRelayProperties properties) {
        this.properties = properties;
    }

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(
            MessageBrokerRegistry registry) {

        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user/");

        StompBrokerRelayRegistration relay =
                registry.enableStompBrokerRelay(
                        "/topic",
                        "/queue");

        relay.setRelayHost(properties.host());
        relay.setRelayPort(properties.port());

        relay.setClientLogin(properties.clientLogin());
        relay.setClientPasscode(properties.clientPasscode());

        relay.setSystemLogin(properties.systemLogin());
        relay.setSystemPasscode(properties.systemPasscode());

        relay.setSystemHeartbeatSendInterval(10_000);
        relay.setSystemHeartbeatReceiveInterval(10_000);

        if (properties.virtualHost() != null
                && !properties.virtualHost().isBlank()) {
            relay.setVirtualHost(properties.virtualHost());
        }
    }
}
~~~

This example uses the Spring Framework 6.1.21 API. In a real system, passcode properties must come from a secret manager or the deployment platform's secret management mechanism. Never put secrets in Git, logs, or error messages.

### 4.3. Distinguishing Client Connections and System Connections

The broker relay maintains two types of connections:

| Connection | Count | Used For |
|---|---:|---|
| System TCP connection | One connection per relay/application instance | Messages sent by server-side code to the broker, not tied to a specific WebSocket client |
| Client TCP connection | One connection per connected WebSocket client | Relaying messages and subscriptions of that client with the broker |

The system connection is used for messages originating from the application, not as the path for receiving broker messages destined for WebSocket clients. Client TCP connections receive messages from the broker and relay them back to the matching WebSocket sessions.

This directly impacts scaling. With 4 application instances and 20,000 total active WebSocket clients, the broker may have to serve roughly 20,000 client TCP connections plus 4 system connections, not counting administrative connections and other clients.

Do not misunderstand the relay as a single connection pool shared across all WebSocket clients. The broker must be sized for the actual number of client connections, subscriptions, throughput, heartbeats, and queue topology.

### 4.4. System Credentials vs. Client Credentials

- `clientLogin`/`clientPasscode` are used for TCP connections opened on behalf of WebSocket clients.
- `systemLogin`/`systemPasscode` are used for the system connection that sends messages from application code, such as HTTP controllers or scheduled jobs.

By design in the broker relay, `CONNECT` frames forwarded on behalf of clients have their login/passcode set by the relay from `clientLogin`/`clientPasscode`. Therefore, any STOMP login/passcode sent by the browser does not determine the broker identity of that connection.

All client connections typically share the broker identity configured in `clientLogin`. Consequently, you cannot assume the broker knows which end-user is acting solely from the broker username. User authentication and destination authorization must be enforced at the Spring/WebSocket layer; broker ACLs control permissions of the relay identities.

## 5. Multi-Node Architecture and Message Flow

Suppose there are two Spring nodes:

- Node A holds Alice's WebSocket session.
- Node B holds Bob's WebSocket session.
- Both relays connect to the same external broker.

### 5.1. Broadcasting from One Node to a Client on Another Node

Bob subscribes to `/topic/orders` through Node B. Alice sends a command to `/app/orders.create` through Node A. The controller on Node A executes the business logic and publishes an event:

~~~java
messagingTemplate.convertAndSend(
        "/topic/orders",
        new OrderCreatedEvent(orderId, status));
~~~

The message flows as follows:

1. Alice sends `/app/orders.create` to Node A.
2. Spring routes the message to `@MessageMapping` on Node A.
3. The service creates the order and returns the result.
4. Node A sends the event to `/topic/orders` through the broker relay.
5. The external broker locates subscriptions for `/topic/orders`.
6. The broker delivers the event to Node B's relay.
7. Node B forwards the event via `clientOutboundChannel` to Bob's WebSocket session.

The same broker destination can be subscribed to by clients across many application instances. The broker handles fan-out; nodes do not need to call each other directly.

### 5.2. Messages from HTTP Requests or Background Jobs

Not only messages originating from WebSocket clients are broadcast through the broker. Any component with a `SimpMessagingTemplate` can send messages:

~~~java
@Service
public class OrderEventPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventPublisher(
            SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(OrderCreatedEvent event) {
        messagingTemplate.convertAndSend(
                "/topic/orders",
                event);
    }
}
~~~

For instance, this can be called from a REST controller, scheduled job, service, or listener. Messages not tied to a specific WebSocket client are sent over the broker relay's system connection.

Thus, if a REST request is routed by the load balancer to Node A, the event can still reach subscribers connected to Node B, C, or D through the shared broker.

### 5.3. Application Destinations Still Run on the Node Holding the Connection

The broker relay does not automatically forward `/app` messages to a controller on an arbitrary node. When a client sends `/app/orders.create`, the message is processed inside the application instance holding that client's WebSocket session.

If a handler needs to distribute work across multiple nodes, design an appropriate broker destination or application event. Do not treat `/app` as a task-distribution queue across servers.

## 6. User Destinations When Users Connect to Different Nodes

This part requires explicit configuration in a multi-application-server model.

### 6.1. User Destinations Are Resolved Using the User Registry

Spring maintains a local `SimpUserRegistry` on each application instance. The registry knows which users/sessions are managed by that node.

For example, Alice subscribes to:

~~~text
/user/queue/notifications
~~~

Node A records Alice's session and translates the logical destination into a unique internal destination for that user/session.

If Node B calls:

~~~java
messagingTemplate.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        notification);
~~~

Node B needs to know where Alice is connected. If only the local registry is used, Node B may fail to find Alice because her session lives on Node A.

### 6.2. Broadcasting the User Registry Across Nodes

`StompBrokerRelayRegistration` provides the API:

~~~java
relay.setUserRegistryBroadcast(
        "/topic/internal.simp-user-registry");
~~~

This configuration lets each node broadcast its local user registry contents and receive broadcasts from other servers. As a result, every node becomes aware of users connected to the remaining nodes.

All application instances must use the same registry broadcast destination and the same external broker. This destination must have broadcast semantics so every node receives registry updates.

### 6.3. Broadcasting Unresolved User Destinations

Configure as well:

~~~java
relay.setUserDestinationBroadcast(
        "/topic/internal.unresolved-user-destination");
~~~

When a node cannot resolve a user destination because the user may be connected on another node, the unresolved message is broadcast so the remaining nodes get a chance to handle it.

The two settings have distinct roles:

| Setting | Purpose |
|---|---|
| `userRegistryBroadcast` | Share user/session information across nodes |
| `userDestinationBroadcast` | Forward unresolved user-destination messages so other nodes can try handling them |

In practice, when sending user-specific messages across nodes is required, configure both on all instances and test with clients actually connected to different nodes. Registry broadcast gives nodes broader visibility; unresolved broadcast handles cases where the current node still cannot locate the target.

### 6.4. Complete User Destination Configuration Example

~~~java
@Override
public void configureMessageBroker(
        MessageBrokerRegistry registry) {

    registry.setApplicationDestinationPrefixes("/app");
    registry.setUserDestinationPrefix("/user/");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost(properties.host())
            .setRelayPort(properties.port())
            .setClientLogin(properties.clientLogin())
            .setClientPasscode(properties.clientPasscode())
            .setSystemLogin(properties.systemLogin())
            .setSystemPasscode(properties.systemPasscode())
            .setUserRegistryBroadcast(
                    "/topic/internal.simp-user-registry")
            .setUserDestinationBroadcast(
                    "/topic/internal.unresolved-user-destination");
}
~~~

Internal destination names must be identical across all nodes. Do not configure Node A with a different registry topic than Node B, or nodes will be unable to share information.

These internal topics carry user/session coordination data. Restrict access and do not allow browser clients to subscribe or publish to them arbitrarily.

### 6.5. Sending Messages to a User

Client subscribes:

~~~text
SUBSCRIBE
id:user-alerts
destination:/user/queue/alerts

^@
~~~

Server sends:

~~~java
messagingTemplate.convertAndSendToUser(
        "alice",
        "/queue/alerts",
        new Alert("ORDER_READY", "Your order is ready"));
~~~

Or use `@SendToUser` in a controller:

~~~java
@Controller
public class OrderNotificationController {

    @MessageMapping("/orders.watch")
    @SendToUser("/queue/order-updates")
    public OrderUpdate watch(
            OrderWatchCommand command,
            Principal principal) {

        return orderService.watch(
                principal.getName(),
                command.orderId());
    }
}
~~~

If the user has multiple sessions, by default messages go to all sessions subscribed to that destination. When you want to reply only to the session that originated the request, use `@SendToUser` with `broadcast=false`.

### 6.6. Cleaning Up Destinations Based on User Lifecycle

User destinations are translated into internal destinations that can vary per session. When a user disconnects, the broker needs to remove temporary queues/subscriptions according to its semantics.

With RabbitMQ, you can use exchange destinations that create auto-delete queues for subscriptions. With ActiveMQ, there are separate mechanisms to purge inactive destinations. Check how your broker handles inactive queues, durable subscriptions, and reconnects; otherwise, unsubscribed queues may linger and accumulate resources.

## 7. Broker-Dependent Destination Semantics

STOMP defines `SEND`, `SUBSCRIBE`, `MESSAGE` frames and the `destination` header, but it does not mandate that all brokers follow the same destination naming conventions. Spring merely forwards the destination prefix to the broker; the broker decides how exchanges, queues, and bindings are created.

### 7.1. RabbitMQ STOMP Plugin Example

RabbitMQ supports STOMP via a plugin:

~~~bash
rabbitmq-plugins enable rabbitmq_stomp
~~~

The default STOMP TCP listener typically uses port 61613 unless configured otherwise. The broker must have the plugin enabled and allow the relay accounts to connect.

RabbitMQ supports several common destinations:

| Destination | Meaning in RabbitMQ STOMP |
|---|---|
| `/topic/name` | Publish/subscribe via a topic exchange; each subscription gets its own queue |
| `/queue/name` | Shared queue; each message is delivered to at most one subscriber |
| `/amq/queue/name` | Access an existing queue without automatically creating a new one |
| `/exchange/name/routing-key` | Send to a specific exchange and routing key |
| `/temp-queue/name` | Temporary queue in a reply-to flow |

With `/topic`, subscription queues are typically non-durable and auto-delete by default. If there are no subscribers, messages sent to the topic may be dropped. With `/queue`, multiple subscribers may compete to receive messages from the same queue; not every subscriber receives a copy.

These semantics belong to the RabbitMQ STOMP adapter, not universal STOMP rules. If using ActiveMQ or another broker, check the corresponding destination prefixes, durable subscriptions, acknowledgements, queue cleanup, and routing syntax.

### 7.2. Broadcast and Work Queues Are Two Different Needs

If you need to send a notification to every user who has the screen open, use a topic/fan-out destination.

If you need to distribute a job to one worker in a pool, use a queue/work-queue destination.

Using a queue for broadcast can cause some clients to miss messages because the broker delivers each message to only one consumer. Using a topic for work meant for a single consumer can cause every subscriber to execute the same side effect.

### 7.3. Offline Messages and Durable Subscriptions

Temporary topic subscriptions typically receive messages only while the subscription is active. If a user is offline and must still receive notifications after logging back in, choose a durable mechanism:

- Broker-supported durable topic subscriptions.
- Dedicated queues with persistence and retention policies.
- Persisting notifications in a database/event store for the client to fetch upon reconnect.
- Combining broker notifications with a state-query API.

Do not assume the broker relay automatically buffers every message for offline users. Delivery guarantees depend on destinations, durability, acknowledgements, and broker configuration.

## 8. Security in the Relay Model

### 8.1. Authenticating WebSocket via HTTP Identity

A STOMP-over-WebSocket session begins with an HTTP handshake. Spring typically attaches the `Principal` from the HTTP request to the WebSocket session and subsequent messages.

Because the broker relay sets `clientLogin`/`clientPasscode` on `CONNECT` frames sent to the broker on the browser's behalf, any login/passcode sent by the browser is not the end-user identity used to authenticate the broker connection.

Your design should include:

- Protecting the HTTP endpoint `/ws` with the application's authentication mechanism.
- Attaching a trusted `Principal` to the WebSocket session.
- Checking `SEND` and `SUBSCRIBE` permissions per destination.
- Never trusting a `username` or `userId` self-declared by the client in payloads/headers.
- Allowing clients to `SEND` only to application prefixes such as `/app`.
- Blocking clients from publishing directly to internal destinations or system topics unless permitted.

### 8.2. Authorization at Spring and the Broker

Because many client connections can share the same broker client identity, the broker does not inherently know whether Alice or Bob sent a given frame. Therefore:

- Spring Security or a `ChannelInterceptor` must authorize actions based on the `Principal`.
- Broker ACLs restrict which exchanges, queues, and virtual hosts each relay identity can access.
- The system identity should have distinct permissions for application-originated messages and internal broadcasts.
- Never use `guest`/`guest` in production.
- Create separate credentials for the client relay and system relay.
- Rotate secrets according to operational policy.

Separating `clientLogin` and `systemLogin` lets the broker enforce different permissions for traffic from client sessions versus server-originated messages. Verify actual broker ACLs and ensure internal broadcast destinations are unreachable by external clients.

### 8.3. Protecting Internal Broadcast Destinations

Destinations such as:

~~~text
/topic/internal.simp-user-registry
/topic/internal.unresolved-user-destination
~~~

are coordination channels between Spring nodes. They are not public APIs for browsers.

If clients can arbitrarily subscribe or publish to these destinations, user/session information may leak or user-destination resolution may be corrupted. Block client access in Spring Security and restrict broker ACLs if supported by the broker.

### 8.4. TLS and Network Boundaries

Browser-to-application connections should use HTTPS/WSS. Application-to-broker connections should run over a controlled internal network or use TLS when crossing untrusted networks.

With RabbitMQ, the STOMP plugin supports a dedicated TLS listener. Configure certificates, trust chains, and the TLS listener on the broker; the relay must use a TLS-enabled TCP client. Do not enable WSS only on the browser side and assume the app-to-broker path is encrypted.

If the broker runs in the cloud, the `virtualHost` configured in the STOMP `CONNECT` `host` header may differ from the TCP hostname the application connects to. These are two separate settings.

## 9. High Availability and Reconnection

### 9.1. Broker Relay Automatically Reconnects the System Connection

The Spring STOMP broker relay maintains a system connection and heartbeats with the broker. By default, send/receive heartbeats are 10 seconds. When disconnected, the relay keeps trying to reconnect, defaulting to roughly every 5 seconds.

You can customize:

~~~java
relay.setSystemHeartbeatSendInterval(10_000);
relay.setSystemHeartbeatReceiveInterval(10_000);
~~~

Heartbeat intervals must align with the broker, load balancers, firewalls, and network idle timeouts. If parties use mismatched heartbeat intervals or overly short timeouts, healthy connections may be treated as dead.

### 9.2. Monitoring `BrokerAvailabilityEvent`

Spring publishes `BrokerAvailabilityEvent` when the system connection to the broker is lost or re-established. Application components can listen for it to pause broker-dependent operations while the broker is unavailable:

~~~java
@Component
public class BrokerAvailabilityListener
        implements ApplicationListener<BrokerAvailabilityEvent> {

    @Override
    public void onApplicationEvent(
            BrokerAvailabilityEvent event) {

        if (event.isBrokerAvailable()) {
            // Broker system connection is ready.
        }
        else {
            // Pause or reject tasks requiring the broker.
        }
    }
}
~~~

This event reflects the state of the relay's system connection. It does not replace monitoring individual WebSocket sessions or client subscriptions.

### 9.3. Client Reconnect and Resubscribe

When the broker or an application node restarts, WebSocket clients may lose their sessions. Clients must:

1. Detect the WebSocket disconnect.
2. Reconnect to the endpoint through the load balancer.
3. Re-authenticate if the session/token has expired.
4. Re-create the STOMP session.
5. Re-subscribe to required destinations.
6. Sync current state from an API/database if messages could have been missed during the gap.

Do not assume old subscriptions are automatically restored after a WebSocket session closes. If messages sent while offline must be preserved, use durable queues/subscriptions or persistent business state.

### 9.4. Broker HA Is a Separate Problem

Having multiple Spring nodes does not mean the external broker has HA. Design separately for the broker:

- An appropriate broker cluster or replication mechanism.
- A load balancer or service endpoint for STOMP TCP/TLS.
- Queue types, replication, and persistence matching message criticality.
- Quorum, failover, backups, and disaster recovery per broker.
- Monitoring connection limits, queue depth, unacked messages, and disk/memory alarms.

By default, the relay reconnects to the same configured host/port. If you need to pick among multiple broker addresses per connection attempt, Spring allows configuring a custom `TcpOperations<byte[]>` via `setTcpClient`. When using a custom TCP client, host/port configured directly on the relay are ignored.

Do not treat reconnect as a no-message-loss guarantee. Reconnect only restores transport connectivity; durability, acknowledgements, and duplicate handling must be built in the broker and application.

## 10. Sizing and Connection Limits

With N WebSocket clients connected to a node, the relay needs roughly N client TCP connections to the broker plus one system connection. Across multiple nodes:

~~~text
Total broker connections
    ≈ sum of WebSocket client connections across all nodes
      + number of application nodes
      + other admin/producer/consumer connections
~~~

For example, with 3 nodes holding 4,000, 3,500, and 2,500 WebSocket clients:

~~~text
Client connections = 4,000 + 3,500 + 2,500
                   = 10,000

System connections = 3

Relay connections  ≈ 10,003
~~~

This is an estimate for the relay, excluding other connections and broker-implementation-specific connections. When scaling, account for:

- TCP connection limits on the broker and OS.
- Memory per connection and per subscription.
- Number of subscriptions per client.
- Heartbeat traffic.
- Message rate and payload size.
- Queue backlog and consumer acknowledgements.
- Connection surge during rolling deployments or reconnect storms.
- Thread, event-loop, and file descriptor limits in the application/broker.

Adding more Spring nodes increases the number of system connections and spreads out WebSocket sessions, but it does not make total broker client connections disappear. The broker must be scaled for the total session count and cluster-wide throughput.

## 11. Monitoring and Operations

Monitor both the application relay and the external broker.

**Spring application side:**

- Current WebSocket sessions per node.
- Disconnect/reconnect counts.
- `BrokerAvailabilityEvent` state transitions.
- Send errors through the broker channel.
- Inbound/outbound message counts, latency, and payload sizes.
- Active subscriptions/user destinations.
- Messages rejected by authorization.

**Broker side:**

- Total STOMP connections and connections per identity.
- Subscription, queue, and consumer counts.
- Queue depth, unacked messages, and message age.
- Publish/deliver/ack rates.
- Unroutable or dropped messages.
- Connection churn, heartbeat timeouts, memory/disk alarms.
- Queues without consumers or uncleaned temporary queues.

Use low-cardinality metric tags such as `protocol`, `destination_template`, `outcome`, and `application_node`. Never put `userId`, `sessionId`, `messageId`, or `traceId` into metric tags. Specific identifiers belong in controlled logs/traces to avoid time-series explosion.

When the system connection is lost, the application may still serve HTTP and WebSocket handshakes yet fail to send messages through the broker as expected. Decide explicitly which endpoints must report unavailable, which tasks can be queued internally, and which must fail fast.

## 12. Testing Multi-Server Distribution

Controller unit tests do not prove the broker distributes messages across nodes. Integration tests with a real external broker or equivalent test environment are required.

### 12.1. Cross-Node Broadcast Test

Setup:

- Start a broker with the STOMP plugin enabled.
- Start two Spring application instances A and B with the same broker configuration.
- Connect STOMP client Alice to node A.
- Connect STOMP client Bob to node B.
- Bob subscribes to `/topic/orders`.
- Alice sends a message via `/app/orders.create`.
- Node A's controller publishes an event to `/topic/orders`.

Assertion: Bob receives the event even though Bob's session is on node B.

### 12.2. Cross-Node User Destination Test

- Alice connects to node A and subscribes to `/user/queue/alerts`.
- Bob or an HTTP request hits node B.
- Node B calls `convertAndSendToUser("alice", "/queue/alerts", payload)`.
- Verify registry broadcast made node B aware of Alice.
- Verify unresolved destination broadcast can forward the message to node A if node B has not resolved it yet.
- Confirm only Alice's sessions receive the message according to the broadcast policy.

This test must verify both `userRegistryBroadcast` and `userDestinationBroadcast`, rather than testing user destinations only when user and sender are on the same node.

### 12.3. Failure and Failover Tests

| Scenario | What to Verify |
|---|---|
| Broker stops while application is running | Availability event flips to unavailable; send policy is explicit |
| Broker restarts | Relay reconnects; client sessions are handled per policy |
| Node A stops | Client reconnects to another node and re-subscribes |
| Node B sends to user on node A | User registry and unresolved destination broadcasts work |
| One node has a misconfigured broker prefix | Test catches that the node misses messages |
| Broker rejects credentials | Relay stays unavailable; logs do not leak passcodes |
| Non-existent queue/topic or wrong semantics | Broker returns an error or message is unrouted; test catches it |
| User disconnects | Temporary queues/subscriptions are cleaned up per broker policy |
| Two nodes process the same event | Idempotency protects side effects if messages are redelivered |
| Broker overloaded or hits connection limit | Backpressure/failure behavior and alerts trigger |

Also run load tests near expected client counts, realistic subscriptions, and representative message rates. A test with only a handful of WebSocket clients is not enough to validate broker connection limits or memory.

## 13. Common Configuration Errors

| Symptom | Common Cause | Where to Check |
|---|---|---|
| Client on node A misses messages sent by node B | Two nodes use separate simple brokers or relay to different brokers | Check `enableStompBrokerRelay` and shared broker endpoint |
| `/app` messages do not reach controller | Wrong application destination prefix or `@MessageMapping` | Check `/app` prefix and mapping after stripping prefix |
| `/topic` messages are not broadcast | Prefix is not relayed or broker lacks destination support | Check relay prefixes and broker destination semantics |
| User-specific messages do not reach other nodes | Missing user registry/unresolved broadcast configuration | Check both broadcast APIs and internal topics |
| Clients receive queue messages unevenly | Using a queue for a broadcast use case | Switch to topic/fan-out semantics |
| Broker sees all clients under the same user | Relay uses shared `clientLogin` for client connections | Enforce end-user authorization at the Spring layer |
| Messages are lost while user is offline | Temporary subscription or topic with no subscribers | Use durable queues/subscriptions or persist notifications |
| Broker accumulates many uncleaned queues | Improper queue/session cleanup | Check auto-delete, expiry, and broker policies |
| Connections close periodically | Mismatched heartbeats or idle timeouts | Check heartbeats on both sides and the load balancer |
| Broker is unavailable yet HTTP still returns success | Application does not check broker state before publishing | Handle `BrokerAvailabilityEvent` and define a failure policy |
| One node can send, another node cannot | Different credentials, vhost, ACL, or network path | Compare configs and broker permissions across nodes |
| Broker restart breaks client delivery | WebSocket/STOMP sessions and subscriptions were lost | Design reconnect, re-authentication, and resubscribe |

## 14. Production Deployment Checklist

Before deploying multiple Spring servers with an external STOMP broker, confirm:

1. The broker supports the required STOMP commands.
2. The STOMP plugin/listener is enabled and network routes from all application nodes to the broker work.
3. All nodes use the same broker endpoint, destination prefixes, and user broadcast destinations.
4. `enableStompBrokerRelay` is used instead of the simple broker when cross-node distribution is required.
5. `/app`, `/topic`, `/queue`, and `/user` have clear boundaries.
6. Client authentication relies on the HTTP/WebSocket `Principal` and authorization is enforced in Spring.
7. Client relay identity and system relay identity have appropriate broker permissions.
8. Internal user registry/unresolved topics are not exposed to browser clients.
9. TLS and secret management are configured for the connection to the broker.
10. Broker connection limits are sized for total cluster-wide WebSocket sessions.
11. Heartbeats, reconnection, `BrokerAvailabilityEvent`, and client resubscription have been tested.
12. User-specific queues/subscriptions have a cleanup policy.
13. Durable messages or offline notifications have an explicit design.
14. Integration tests verify broadcasts and user destinations across at least two application nodes.
15. Broker HA, persistence, queue policies, and backups are operated separately.
16. Monitoring covers both the application relay and the broker.

## Takeaways

An external STOMP broker solves subscription and message distribution across multiple Spring application servers. Each node still manages local WebSocket sessions, while the broker relay forwards broker destinations to a shared broker.

In Spring Framework, `enableStompBrokerRelay` configures destination prefixes and returns `StompBrokerRelayRegistration` to set host, port, credentials, heartbeats, and broadcast destinations. The broker relay maintains one system connection for application-originated messages and one client connection per WebSocket client.

For cross-node user destinations, configure `userRegistryBroadcast` to share the user registry and `userDestinationBroadcast` to forward unresolved messages. Protect internal destinations, authenticate users at the WebSocket layer, and enforce authorization in both Spring and the broker.

Finally, the broker relay does not by itself guarantee message durability or HA. Those depend on the broker, destinations, acknowledgements, queue policies, persistence, and client reconnection logic. Test with multiple application instances and a real broker before considering the system production-ready.

## References

- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework 6.1.21 — StompBrokerRelayRegistration API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)
- [Spring Framework 6.1.21 — MessageBrokerRegistry API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [Spring Framework — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [RabbitMQ — STOMP Plugin](https://www.rabbitmq.com/docs/stomp)
