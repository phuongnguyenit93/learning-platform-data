# Choosing Simple Broker vs. Broker Relay Based on System Requirements

> Scope: Spring Framework STOMP over WebSocket, Java 17+. This article explains the two message broker options in Spring, how to configure them, their differing capabilities, and decision criteria based on scale, load capacity, reliability, and operations. The code snippets are configuration inside a Spring application, not standalone Java programs.

## 1. Role of the Broker in STOMP Architecture

In a STOMP application, WebSocket provides a bidirectional connection between client and server, while STOMP defines frames such as CONNECT, SEND, SUBSCRIBE, MESSAGE, ACK, and DISCONNECT. Spring receives frames from clients, routes application messages to controllers, or forwards messages to a broker for distribution to subscribers.

A typical flow:

1. A client connects to the WebSocket endpoint, e.g., /ws, then sends STOMP CONNECT.
2. The client SENDs to /app/chat.send. The /app prefix is reserved for application messages.
3. Spring routes to the corresponding @MessageMapping method.
4. The controller returns a payload or the application proactively sends via SimpMessagingTemplate.
5. The message is passed to brokerChannel.
6. The broker distributes the message to clients that SUBSCRIBEd to matching destinations, via clientOutboundChannel.

Spring provides two ways to handle the broker part:

- **Simple broker**: a lightweight broker built into the Spring application process.
- **STOMP broker relay**: Spring forwards STOMP frames to an external message broker over TCP, such as a STOMP-capable broker.

Both work with Spring's controller, destination, and subscription model. The main differences lie in broker capabilities, scalability, reliability, and operational cost.

## 2. What Is the Simple Broker?

The simple broker is a minimal broker handler built into Spring WebSocket. It tracks active subscriptions in the application's memory and distributes messages to subscribers with matching destinations.

Basic configuration:

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
    }
}
~~~

With this configuration:

- Clients SEND to /app/... to invoke controllers with @MessageMapping.
- Clients SUBSCRIBE to /topic/... or /queue/... to receive messages distributed by the simple broker.
- Controllers can return values with @SendTo, or send proactively via SimpMessagingTemplate.
- The simple broker stores subscription information in the memory of the running process.

### Capabilities and Limitations

The simple broker suits basic publish/subscribe flows. It can distribute messages to multiple subscribers, handle subscription registration and unregistration, and run without installing a separate broker.

However, this is not a full STOMP broker. It does not support advanced protocol features such as ACK/NACK and receipts the way a full STOMP broker can. It does not provide durable queues, retaining messages for replay after a client disconnects, or a broker clustering mechanism. Subscription state and message distribution live in the memory of a single Spring application instance.

If an application runs two instances behind a load balancer, each instance has its own simple broker and its own set of subscriptions. A client connected to instance A does not automatically receive messages sent via the simple broker on instance B. Sticky sessions do not turn two simple brokers into one shared broker; they only affect which instance a client is routed to.

### Heartbeats with the Simple Broker

The simple broker does not send STOMP heartbeats by default. You can configure heartbeats and a TaskScheduler to check connections:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    private final TaskScheduler heartbeatScheduler;

    public WebSocketConfig(TaskScheduler heartbeatScheduler) {
        this.heartbeatScheduler = heartbeatScheduler;
    }

    @Bean
    public TaskScheduler heartbeatScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        return scheduler;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[] {10000, 10000})
                .setTaskScheduler(heartbeatScheduler);
    }
}
~~~

This is an illustrative configuration for a 10-second heartbeat in each direction. In a real application, verify the Spring version in use, scheduler configuration, proxy/load balancer timeouts, and client-side heartbeats. Heartbeats help detect inactive connections; they do not turn the simple broker into a broker with durable storage or clustering capabilities.

## 3. What Is the STOMP Broker Relay?

The broker relay is a Spring component that receives messages from internal channels and forwards STOMP frames to an external broker over TCP. The external broker handles destination management, subscriptions, and message distribution.

Several popular brokers support STOMP via connectors or plugins, such as RabbitMQ with the STOMP plugin and ActiveMQ with the STOMP transport. The specific broker and version determine which STOMP features are available as well as how destinations are configured.

Basic configuration:

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

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setRelayHost("broker.internal")
                .setRelayPort(61613)
                .setClientLogin("web-client")
                .setClientPasscode("client-secret")
                .setSystemLogin("spring-system")
                .setSystemPasscode("system-secret");
    }
}
~~~

The host, port, usernames, and passwords above are example values only. Retrieve them from environment configuration or a secret manager; do not hardcode real credentials in source code. The STOMP port depends on broker configuration; 61613 is common in some RabbitMQ/ActiveMQ setups but is not a mandatory port for every broker.

### Two Types of TCP Connections Managed by the Relay

Spring's STOMP broker relay maintains:

1. **System connection**: one TCP connection used for messages sent to the broker by the Spring application itself, such as messages sent via SimpMessagingTemplate.
2. **Client connections**: a separate TCP connection to the broker for each WebSocket/STOMP client served by the relay. The relay forwards frames from the client over its corresponding connection and brings frames sent back by the broker to the client through Spring.

Thus, the broker relay enables multiple Spring instances to share the same external broker infrastructure. However, client connection counts, broker connection limits, file descriptors, memory, and bandwidth must be sized for concurrent connections. The relay does not eliminate connection costs; it shifts message distribution management to a dedicated broker.

Authentication properties have distinct meanings:

- clientLogin/clientPasscode are credentials the relay uses when connecting to the broker on behalf of clients.
- systemLogin/systemPasscode are credentials used for the application's system connection.
- The broker still needs access permissions, destinations, and policies configured appropriately for those accounts.

## 4. Direct Comparison

| Criterion | Simple broker | STOMP broker relay |
|---|---|---|
| Component | Built into the Spring application | Spring relay connected to an external broker |
| Infrastructure | No separate broker installation needed | Requires deploying and operating a STOMP-capable broker |
| Subscription state | In memory of each Spring instance | Managed by the external broker |
| Delivery scope | Within the instance holding the connection | Can distribute across multiple Spring instances sharing a broker |
| Advanced STOMP | Limited feature set; no full ACK/NACK and receipts | Can use broker-supported features such as ACK, receipts, transactions |
| Message storage | Does not provide durable queues or replay by default | Can use queues/durable subscriptions/persistence if supported and configured by the broker |
| Heartbeat | Requires configuring a scheduler to enable | Relay has heartbeat support with the broker; configure per requirements and broker |
| Scalability | Fits small or single-instance applications | Better suited when multiple instances and a shared broker are needed |
| Operations | Simpler, fewer moving parts | Requires monitoring the broker, relay connections, permissions, and capacity |
| Testing | Easy to use for development and basic integration tests | Requires a real broker or production-equivalent test environment |

Do not interpret this table as meaning every external broker provides every feature. The broker relay only forwards the protocol; ACK, receipts, transactions, durable queues, retention periods, dead-lettering, and clustering depend on the specific broker, plugin, version, and configuration.

## 5. Distinguishing Destination Prefixes and Broker Semantics

A configuration typically has three destination groups:

| Prefix | Purpose |
|---|---|
| /app | Inbound messages destined for Spring controllers via @MessageMapping. |
| /topic | Typically used for publish/subscribe or broadcast. |
| /queue | Typically used for queue flows or private messages. |

The /app prefix belongs to Spring's application routing layer. It continues working the same way when switching from the simple broker to the broker relay.

By contrast, /topic and /queue are destinations handed off to the broker to process. With the simple broker, they are primarily names/prefixes for Spring to match subscriptions and distribute messages. With an external broker, the exact meaning of a destination depends on the broker. For example, a broker might map a topic to an exchange or a queue to a named queue; some brokers require pre-creating destinations, configuring permissions, or setting destination auto-creation rules.

Therefore, do not assume a destination like /queue/notifications behaves identically across all brokers. Read the chosen broker's documentation and align conventions across clients, the Spring application, and the broker.

Controllers can still remain unchanged:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

Clients send to /app/chat.send and subscribe to /topic/chat. Spring still takes the handler result and passes the message through brokerChannel. The difference is whether the message is distributed by the in-process simple broker or relayed to an external broker.

## 6. When to Choose the Simple Broker?

The simple broker is usually a reasonable choice when:

- The application is small, with moderate traffic and concurrent connections.
- Running a single Spring instance, or distribution scoped to a single instance is acceptable.
- Only basic SEND, SUBSCRIBE, and broadcast are needed.
- ACK/NACK, receipts, transactions, or durable queues are not required.
- Retaining messages for clients to receive after going offline is not needed.
- You want fewer infrastructure components and fast deployment.
- Developing features, prototyping, or running integration tests that do not need to verify a production broker.

Example: an internal dashboard showing only the progress of a job running on a single instance, where online clients on that same instance receive updates and primary data is still stored in a database. If a client disconnects, the dashboard can reload the latest state from an API upon reconnecting.

Do not choose the simple broker merely because it is easy to configure if the system already has clear requirements for multi-instance distribution, message durability, or protocol features that the simple broker does not satisfy.

## 7. When to Choose the Broker Relay?

The broker relay is appropriate when one or more of the following requirements exist:

- Multiple Spring instances need to distribute messages through a shared broker.
- Message volume or subscriber count requires management by a dedicated broker.
- STOMP ACK/NACK, receipts, transactions, or advanced broker features are required.
- Durable queues, durable subscriptions, or message retention while subscribers are offline are needed, provided the broker supports and is configured for them.
- You want to decouple the broker lifecycle from the Spring application deployment lifecycle.
- The system needs routing policies, destination authorization, monitoring, and message administration at the broker layer.

Example: a notification system with multiple WebSocket instances behind a load balancer. User A connects to instance 1, user B connects to instance 2; when a service publishes an event to the shared broker, subscribers on both instances can receive the message via the relay and broker.

The relay also increases operational responsibility: you must deploy the broker, configure networking, credentials, ACLs, monitoring, capacity, backups, or clustering as needed. The broker relay does not automatically guarantee durable message storage; the application must select and properly configure the broker's queues, exchanges, subscriptions, and persistence.

## 8. Decision Matrix by System Requirements

| Question | If the Answer Is "Yes" | Selection Direction |
|---|---|---|
| Running only one Spring instance and needing basic broadcast? | No cross-instance distribution needed. | Simple broker may suffice. |
| Need multiple Spring instances publishing and receiving together? | Need a shared broker across instances. | Broker relay. |
| Need STOMP ACK/NACK or receipts? | Need advanced protocol features. | Broker relay with a broker supporting those features. |
| Need durable queues/subscriptions or offline message retention? | Need broker-managed storage semantics. | Broker relay with appropriate persistence configuration. |
| No team or platform to operate a broker? | Additional infrastructure is a major burden. | Prefer simple broker if functional requirements allow. |
| Have SLA, observability, and centralized message control requirements? | Need a broker with monitoring and governance policies. | Generally leans toward broker relay. |

There is no fixed connection-count or throughput threshold to decide in place of measurement. Benchmark with realistic payloads, publish rates, fan-out, subscription counts, and networking. Check p95/p99 latency, CPU, heap, connection counts, and behavior when the broker or an app instance fails.

## 9. Scaling, Reliability, and Security Considerations

### Multi-Instance Scaling

With the simple broker, each instance holds subscriptions for WebSocket sessions connected to that instance. When a message is broadcast on another instance, there is no shared broker mechanism to forward it automatically. If cross-instance delivery is required, you must add another synchronization mechanism or switch to a broker relay.

With the broker relay, Spring instances connect to the same broker or broker cluster. The broker is responsible for delivering to subscriptions registered through the relays. The design must still account for broker clustering, partitions, network failures, and destination configuration.

### Reliability and Offline Messages

WebSocket is a real-time connection; an offline subscriber does not mean messages are automatically saved. The simple broker does not provide durable queues. An external broker may support persistence, durable subscriptions, ACK, and replay, but each feature must be enabled and used with the right semantics.

If the business requires never losing notifications, store events or state in a database/outbox and provide a resync mechanism when clients connect. Do not rely solely on clients subscribing to a topic as a long-term data source.

### Security

- Allow clients to connect only to the application endpoint; do not expose the STOMP broker port directly to the Internet without a valid reason and proper protection layers.
- Protect relay-to-broker communication with network policies and TLS when required by the environment.
- Manage client credentials and system credentials separately under the principle of least privilege.
- Configure ACLs on the broker for required destinations and operations.
- Enforce WebSocket/STOMP authentication and SEND/SUBSCRIBE authorization in Spring Security or the broker per your design.
- Do not trust self-declared destinations or usernames from clients when handling private data.

### Observability and Operations

When using the relay, monitor client connection counts, system connections, reconnects, heartbeat timeouts, message rates, queue depth, consumer lag, broker memory/disk, and authorization errors. Set up alerts for broker unavailability, abnormal queue growth, and rejected connections.

## 10. Migrating from Simple Broker to Broker Relay

A migration path can follow these steps:

1. Identify mandatory requirements: multiple instances, ACK/NACK, receipts, durable queues, throughput, latency, and SLAs.
2. Select a STOMP-capable broker; check versions, plugins/connectors, destination semantics, and broker limits.
3. Deploy the broker in a dev or staging environment; open the network path from Spring instances to the STOMP port.
4. Create separate credentials for client relay and system connections; configure least-privilege ACLs.
5. Replace `enableSimpleBroker(...)` with `enableStompBrokerRelay(...)` and configure the appropriate host, port, credentials, and heartbeats.
6. Keep the /app application destination prefix and re-verify /topic, /queue, and /user destinations against broker semantics.
7. Test SEND, SUBSCRIBE, @SendTo, SimpMessagingTemplate, user destinations, reconnects, multiple instances, and behavior when the broker stops.
8. Measure performance and monitor connections, message rates, and queue depth before deploying to production.

You do not need to rewrite all @MessageMapping methods simply because you changed brokers. Controllers and client APIs can stay the same if destination semantics and access permissions are preserved. However, previous assumptions about queues, topics, subscriptions, and offline messages must be re-verified.

## 11. Common Pitfalls

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Relay cannot connect to broker | Wrong host/port, STOMP plugin not enabled, firewall, or invalid credentials | Check relay logs, STOMP port, and broker logs. |
| Client SEND succeeds but subscribers do not receive | Destination not handled by broker or ACL rejected | Check destination, broker routing, and publish/subscribe permissions. |
| Messages only reach clients on one instance | Application still uses per-instance simple broker or relays point to different brokers | Check registration type and broker address on every instance. |
| /queue behaves differently after switching brokers | Broker destination semantics differ from simple broker | Read broker documentation and configure queues/exchanges accordingly. |
| Client goes offline then reconnects without seeing old messages | Durable queue/subscription or message persistence not configured | Check queue type, subscription, ACK, and retention policy. |
| Broker rejects many connections | Connection limit or insufficient capacity | Measure concurrent WebSocket clients and relay connections to the broker. |
| Dead connections not detected in time by client | Heartbeats, proxy timeouts, or reconnect not configured properly | Check bidirectional heartbeats, timeouts, and reconnect strategy. |
| System messages fail to send while clients remain connected | System connection or system credentials error | Check system connection logs and system user permissions. |

## 12. Selection Conclusion

Choose the simple broker when the system only needs basic pub/sub within a single Spring instance and wants minimal infrastructure. Choose the broker relay when you need a shared broker across multiple instances, advanced protocol features, or queues and persistence provided by a dedicated broker.

The final decision should be based on functional requirements, actual load, reliability targets, operational capabilities, and the true capabilities of the chosen broker. The broker relay is an integration path to message broker infrastructure; it does not automatically turn every destination into a durable queue or guarantee zero message loss.

## References

- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html): enabling the simple broker, destination prefixes, and limitations of the built-in broker.
- [Spring Framework — STOMP Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html): connecting to an external broker, system connection, and client connections.
- [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html): endpoint configuration, application prefixes, and message broker setup.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): message flow between client, application, and broker.
