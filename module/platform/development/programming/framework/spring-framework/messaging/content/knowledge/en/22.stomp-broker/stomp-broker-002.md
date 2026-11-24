# Feature Limitations, Durability, and Scalability of the Simple Broker in Spring STOMP

## Learning Objectives

After this lesson, you can:

- Explain what state Spring's Simple Broker stores and how it distributes messages.
- Identify Simple Broker limitations regarding the STOMP command set, delivery acknowledgments, message storage, and subscriptions.
- Distinguish prefixes like /topic and /queue from the actual semantics of a message queue.
- Analyze why the Simple Broker fits small, single-instance applications and disposable real-time data.
- Decide when to transition to a STOMP Broker Relay and an external message broker.
- Design testing, observability, and troubleshooting when the broker or client connections are interrupted.

This article focuses on Spring Framework STOMP over WebSocket. The Simple Broker is a built-in broker running in the memory of the application process. It is a lightweight option to get started, experiment, and broadcast real-time notifications within a simple application.

## 1. What is the Simple Broker?

When enabling STOMP with Spring's WebSocket configuration, the application can route messages to two main places:

1. Handler methods in controllers, typically annotated with @MessageMapping.
2. The message broker, which manages subscriptions and broadcasts messages to subscribed clients.

The Simple Broker is Spring's built-in broker component. It receives SUBSCRIBE requests, stores subscription information in memory, and broadcasts messages to connected clients with matching destinations. The broker supports path-based destinations and Ant-style patterns.

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

In this configuration:

- Clients connect over WebSocket to the /ws endpoint.
- Messages with destinations starting with /app are routed to application handlers.
- Messages with destinations starting with /topic or /queue are routed to the Simple Broker.
- Server-side handlers or services can broadcast messages via SimpMessagingTemplate so the broker distributes them to matching subscriptions.

High-level message flow:

~~~text
WebSocket client
      |
      | STOMP SEND / SUBSCRIBE
      v
clientInboundChannel
      |
      +---- destination /app/... ------> @MessageMapping controller
      |                                      |
      |                                      | send message via brokerChannel
      |                                      v
      +---- destination /topic/... ---> Simple Broker
                                             |
                                             | find matching subscriptions
                                             v
                                      clientOutboundChannel
                                             |
                                             v
                                      WebSocket clients
~~~

The Simple Broker manages delivery within the Spring process itself. It is not a standalone broker service running on a separate server, nor does it automatically create a long-term message store.

## 2. What Does the Simple Broker Store in Memory?

The Simple Broker stores the subscription state of currently connected clients. When a client sends SUBSCRIBE, the broker records the session, subscription, and destination so it can route subsequent messages. When the client unsubscribes or the session ends, the corresponding state is cleaned up.

Key distinctions:

- **Subscription state:** information about which client is listening to which destination. The Simple Broker stores this part in memory.
- **Message payload:** the content of messages broadcast to matching subscriptions. The Simple Broker is not a message store for retaining history and replaying messages later.
- **Business state:** the application's business data, such as orders, transactions, or job statuses. This data must be stored in the application's database or appropriate storage system.

For example, client A is subscribed to /topic/orders. When the server broadcasts a notification to that destination, the Simple Broker distributes the notification to existing matching subscriptions. If a client is not yet connected or has disconnected at the time of broadcast, do not assume the broker keeps the message for that client to receive upon connecting later.

When the Spring process stops or restarts, subscription state in memory is lost. Clients must reconnect and re-register their subscriptions. The Simple Broker does not restore old subscriber lists from disk.

Therefore, treat the Simple Broker as a mechanism for pushing live notifications to currently listening clients, rather than an event store or a job queue.

## 3. Limitations on the STOMP Feature Set

The Simple Broker only supports a subset of STOMP commands and features. According to the Spring documentation, features such as ACK and RECEIPT are not supported, along with several other features of a full-featured broker.

### 3.1 No Broker-Level ACK Mechanism

ACK is the mechanism for a client to acknowledge message processing according to acknowledgment modes supported by a broker. If an application needs consumer processing acknowledgments, detection of unacknowledged messages, or requests for the broker to redeliver messages, the Simple Broker does not provide full support for that mechanism.

The fact that a client receives a MESSAGE frame over the connection does not mean the client's business logic has processed and saved it successfully. If business acknowledgment is needed, design a custom application protocol—for example, the client sends an acknowledgment message with an event ID, and the server persists the acknowledgment result durably.

### 3.2 No Broker RECEIPT

STOMP RECEIPT allows a client to request a broker response confirming that a frame was processed according to protocol conventions. The Simple Broker does not support RECEIPT like a full STOMP broker.

Consequently, you should not build logic that depends on sending SEND or SUBSCRIBE with a receipt header and waiting for a RECEIPT from the Simple Broker.

### 3.3 Not a Full STOMP Broker

STOMP defines many commands and capabilities. The Simple Broker is designed to cover a basic set serving subscribe and broadcast use cases. When business requirements depend on advanced broker features, check the capabilities of the chosen external broker and configure it accordingly.

Do not infer that just because an application uses STOMP, every command or delivery mode in the STOMP specification is automatically supported by Spring's Simple Broker.

## 4. Limitations on Durability and Message Delivery

Durability is the ability to preserve data or messages across failures, restarts, and periods of consumer inactivity. The Simple Broker does not provide message persistence or durable subscriptions like a dedicated message broker.

### 4.1 No Message Persistence

The Simple Broker does not write messages to disk or a persistent store so they can be recovered after a process stops. If an application broadcasts a message and then the process stops, the Simple Broker cannot replay that message after startup.

### 4.2 No Offline Queues for Subscribers

A subscription in the Simple Broker is bound to a connected client. If the client is offline when a message is broadcast, the broker does not store a copy of the message to redeliver when the client returns.

Example:

1. Client A subscribes to /topic/notifications.
2. Client A disconnects.
3. The server broadcasts a notification.
4. Client A reconnects and re-subscribes.
5. The Simple Broker has no history of missed notifications to replay automatically.

If users need to see past notifications, the application must read them from a database or history API, and use STOMP to notify that new data is available.

### 4.3 No Durable Subscriptions Across Restarts

Subscriptions are held in memory and tied to the client session. After the application process stops, the broker does not restore subscriptions from durable storage. Clients need to reconnect and resubscribe.

### 4.4 No End-to-End Business Processing Guarantees

A message sent over WebSocket can be affected by network drops, closed tabs, inactive clients, payload conversion errors, or receiver-side processing errors. The Simple Broker does not turn a broadcast stream into a reliable business transaction.

If an important event such as payment, balance change, order placement, or approval must be preserved, persist the business event first. Then broadcast a notification so the client refreshes its UI. The client can use an event ID or version to call a sync API if it detects missing data.

Common design pattern:

~~~text
Business request
      |
      v
Database transaction
      |
      +---- update business data
      |
      +---- write event to outbox
                    |
                    v
             Background publisher
                    |
                    v
              Message broker
                    |
                    v
              STOMP / WebSocket
                    |
                    v
              Connected clients
~~~

The outbox ensures the application does not lose the intent to emit an event when a business transaction has committed but message sending fails. A worker can retry sending the outbox record. The receiving side should still handle messages idempotently because retries can produce duplicate messages.

## 5. Why Doesn't /queue Automatically Become a Real Queue?

A destination name in STOMP is a string whose semantics are defined by the broker. In many systems, /topic is commonly used for publish-subscribe and /queue often suggests point-to-point. However, prefixes are merely routing conventions; actual semantics depend on the broker handling the destination.

The Simple Broker broadcasts messages to connected clients whose subscriptions match the destination. Therefore, if three clients subscribe to /queue/tasks on the Simple Broker, all three can receive the same message broadcast to that destination.

The name /queue/tasks does not automatically create the following features:

- Ensuring a message is received by only one consumer in a group.
- Retaining messages for later consumers.
- Removing a message from the queue only after acknowledgment via ACK.
- Redelivering unacknowledged messages.
- Having the queue exist independently of the Spring application's lifecycle.

This is an important distinction between a destination named /queue and an actual queue managed by a message broker.

If you need competing consumers, background jobs, retries, dead-letter queues, or buffering pending messages, use a dedicated broker and configure queues according to that broker's documentation.

## 6. Scaling and Clustering Limitations

The Simple Broker runs in the memory of a single Spring instance. Each instance has its own set of subscriptions. It is not a distributed broker, and Spring explicitly states that the Simple Broker is not suitable for clustering.

Suppose two instances are deployed behind a load balancer:

~~~text
                 Load balancer
                  /         \
                 v           v
          Spring node A   Spring node B
          Simple Broker   Simple Broker
          subscriptions   subscriptions
                 |           |
              Client A    Client B
~~~

If Client A connects to node A and Client B connects to node B, each Simple Broker only knows about subscriptions on its own node. A message broadcast locally on node A is not automatically shared with the Simple Broker on node B.

This leads to several risks:

- Users on different nodes may not receive the same broadcast.
- Outcomes depend on which node holds the WebSocket session.
- Increasing the number of application instances does not automatically increase system-wide message delivery reach.
- Sticky sessions only keep a client pinned to one node; they do not synchronize subscriptions or messages across nodes.
- When a node is replaced or restarted, that node's subscriptions are lost and clients must reconnect.

For a single-instance application, this scope may be completely suitable. When running multiple nodes is required, a shared broker component is needed so all nodes route messages and subscriptions together.

## 7. Performance and Resource Limitations

The Simple Broker uses a simple message-dispatch loop. For each message, the broker must find matching subscriptions and deliver the message to the corresponding clients. As the number of clients, subscriptions, send rate, or recipients per message increases, the distribution work and state storage grow accordingly.

Contributing factors:

- Number of active WebSocket sessions.
- Number of subscriptions per session.
- Number of destination patterns to match.
- Rate of messages sent to the broker.
- Number of subscribers receiving each message.
- Payload size.
- Outbound bandwidth and client processing speed.
- Thread counts and channel configurations in the application.

Spring does not prescribe a fixed client-count threshold applicable to all systems. Load capacity depends on hardware, thread configuration, payloads, patterns, broadcast frequency, network conditions, and client behavior. Do not invent a universal maximum number and treat it as an official Simple Broker limit.

Measure in an environment close to production. Load tests should simulate realistic session counts, subscriptions, message rates, payload sizes, and fan-out ratios. Monitor CPU, heap, GC, connection counts, publish-to-client latency, outbound throughput, send errors, and disconnected session counts.

When exceeding the capacity of a single instance, increasing CPU or heap can help to a certain extent, but it does not solve the architectural limitation regarding clustering. If distributed broadcasting is required, move the broker layer to a system designed for it.

## 8. Heartbeats Help Detect Connections, Not Create Durability

The Simple Broker can support STOMP heartbeats when configured with a TaskScheduler. Heartbeats help detect inactive connections and assist with connection state management.

Example broker configuration snippet:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableSimpleBroker("/topic", "/queue")
            .setHeartbeatValue(new long[] {10_000, 10_000})
            .setTaskScheduler(messageBrokerTaskScheduler);

    registry.setApplicationDestinationPrefixes("/app");
}
~~~

In the example, messageBrokerTaskScheduler is a TaskScheduler bean provided by the application. The two heartbeat values are specified in milliseconds for send and receive intervals per STOMP configuration.

Heartbeats are useful for detecting silent or broken connections. They do not:

- Write messages to disk.
- Recover missed messages.
- Preserve subscriptions across application restarts.
- Confirm that the client completed business processing.
- Synchronize subscriptions across multiple nodes.

Do not confuse heartbeats with ACK, RECEIPT, or retry mechanisms. They solve different problems.

## 9. When Should You Use the Simple Broker?

The Simple Broker is suitable when:

- The application is small or in the development stage.
- Deployment consists of only a single Spring instance.
- Clients mainly need live notifications while connected.
- Messages can be regenerated or clients can re-fetch data via an API.
- ACK, RECEIPT, durable queues, or offline delivery are not needed.
- Losing subscriptions on process restart is acceptable.
- Actual load has been measured and falls within a single instance's capacity.

Suitable examples:

- Dashboards displaying the latest metrics.
- Admin pages updating the status of running jobs.
- Simple internal chat where chat history is stored separately in a database.
- Monitoring screens for online devices.
- UI notifications prompting the client to reload an updated record.

In these examples, the database or API remains the primary source of truth. STOMP simply helps the UI receive update signals faster.

## 10. When Do You Need an External Broker and Broker Relay?

Consider an external broker when the application needs:

- Multiple Spring instances publishing and receiving messages together.
- Clustering or message distribution across nodes.
- ACK, RECEIPT, or advanced STOMP features supported by the broker.
- True queues, competing consumers, or complex routing policies.
- Durable subscriptions, persistent messages, retries, or dead-letter queues.
- Message coordination across multiple services or applications.
- Decoupling the broker lifecycle from the lifecycle of individual Spring processes.

Spring supports connecting to an external broker via the STOMP Broker Relay. The broker relay is a MessageHandler that forwards messages over TCP to a STOMP-capable message broker and relays messages received from the broker down to WebSocket sessions.

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
        registry.enableStompBrokerRelay("/topic", "/queue");
    }
}
~~~

This example illustrates replacing the Simple Broker with a broker relay. The application must install and run an external broker that supports STOMP, then configure the appropriate host, port, credentials, virtual host, and destination prefixes.

Commonly used brokers include RabbitMQ (with the STOMP plugin) and ActiveMQ. Read the specific broker's documentation to learn how to enable STOMP, create exchanges/queues, set permissions, and configure persistence, ACK, retries, dead-lettering, and resource limits.

The broker relay does not create durability on its own. It forwards messages to the external broker. For persistent messages, you must configure persistence and appropriate queues/subscriptions on that broker. Support for ACK, receipts, durable subscriptions, and routing also depends on the actual product, version, protocol, and configuration.

## 11. What Connections Does the Broker Relay Maintain?

Spring STOMP Broker Relay uses two groups of TCP connections:

1. **System connection:** a single connection maintained by Spring to forward messages originating from the server application to the broker.
2. **Client connections:** a separate TCP connection for each connected WebSocket client; the relay forwards the client's STOMP frames over its corresponding connection to the broker.

High-level structure:

~~~text
Spring application
   | 
   +---- system TCP connection -------------------+
   |                                               |
   +---- client A TCP connection -----------------+--> External STOMP broker
   |                                               |
   +---- client B TCP connection -----------------+
   |
   +---- client C TCP connection -----------------+
   
WebSocket clients <---- Spring relay <----> External broker
~~~

Because each WebSocket client has a corresponding TCP connection to the broker, the design must account for the broker's connection and resource limits. Increasing the number of WebSocket clients means increasing the number of client-side connections the relay must maintain to the broker.

The relay has a mechanism to retry reconnecting the system connection when the broker temporarily disconnects. However, client WebSocket/STOMP connections are not automatically restored simply because the system connection recovered. Clients need logic to reconnect and re-subscribe.

## 12. Monitoring Status and Handling Failures with the Broker Relay

Spring publishes the ApplicationContext event BrokerAvailabilityEvent to notify when the broker relay's system connection is lost or re-established. Server components can listen to this event to know when the broker is ready to receive messages.

Example:

~~~java
@Component
public class BrokerStatusListener
        implements ApplicationListener<BrokerAvailabilityEvent> {

    @Override
    public void onApplicationEvent(BrokerAvailabilityEvent event) {
        if (event.isBrokerAvailable()) {
            // Broker system connection is ready
        } else {
            // Broker system connection is currently unavailable
        }
    }
}
~~~

This is a signal about the relay's system connection status, not proof that all client sessions are active or that all messages have been processed.

When using SimpMessagingTemplate to broadcast messages through the relay, the application should be prepared to handle MessageDeliveryException if the broker is unavailable or sending fails. For critical business events, keep events in an outbox or durable store so they can be re-sent.

Other events useful for session management:

- SessionConnectEvent: notifies when STOMP CONNECT starts.
- SessionConnectedEvent: notifies that the STOMP session has been established.
- SessionSubscribeEvent: notifies that a client registered a subscription.
- SessionUnsubscribeEvent: notifies that a client canceled a subscription.
- SessionDisconnectEvent: notifies that the STOMP session ended.

SessionDisconnectEvent may be published more than once for the same session in certain situations. Listeners need idempotent handling—for example, only marking offline when the current state actually needs to change.

## 13. Comparing Simple Broker and External Broker Relay

| Criterion | Simple Broker | External Broker Relay |
|---|---|---|
| Where it runs | Inside the Spring process | External STOMP broker, forwarded by Spring |
| Subscription state | In memory of a single instance | Managed by the external broker per its capabilities |
| Delivery scope | Matching clients on the same instance | Can be shared across multiple instances using a shared broker |
| Clustering | Not suitable | Supports distributed architectures depending on broker |
| ACK and RECEIPT | Not fully supported; Spring states no ACK/RECEIPT | Depends on the broker's STOMP features |
| Message persistence | No durable message store | Configurable if supported by the broker |
| Offline/durable subscriptions | No built-in durable subscriptions | Possible, depending on broker and configuration |
| Operations | Fewer components, easy to start | Requires operating, securing, and monitoring a separate broker |
| Suitable scenarios | Ephemeral broadcasts, single instance | Multi-node systems, advanced broker requirements |

This table describes general capabilities. When choosing an external broker, check official documentation and test the exact version and configuration to be deployed.

## 14. Decision and Migration Workflow

Before keeping the Simple Broker, answer the following questions:

1. If a client goes offline for a few minutes, does it need to receive all missed messages?
2. If the Spring process restarts, do subscriptions and messages need to be recovered?
3. Does a message need to be processed by only one consumer in a group?
4. Does the application require ACK, RECEIPT, retries, or dead-letter queues?
5. Do multiple Spring instances need to share the same broadcast stream?
6. Has the actual load been tested to confirm it fits within a single instance's capacity?

If all answers indicate that messages are merely ephemeral real-time signals, the Simple Broker may be a reasonable choice.

If you need durable delivery, reliable background processing, multiple consumers, or clustering, choose a dedicated broker. The migration process typically includes:

1. Choose a broker that supports STOMP and meets requirements for persistence, ACK, queues, and HA.
2. Install, enable the STOMP endpoint, and configure access permissions on the broker.
3. Replace enableSimpleBroker with enableStompBrokerRelay using the appropriate prefixes.
4. Configure host, port, credentials, virtual host, and connection limits.
5. Create queues/exchanges/subscriptions along with durable, persistent, retry, or dead-letter policies on the external broker.
6. Test ACK, RECEIPT, reconnects, broker restarts, application restarts, and multiple instances.
7. Monitor BrokerAvailabilityEvent, send errors, connection counts, and latency.
8. Update clients to reconnect, resubscribe, and sync missed data via API when needed.

@MessageMapping controllers and SimpMessagingTemplate can usually retain the same programming model. Changes primarily lie in broker configuration and the delivery guarantees the application chooses to use.

## 15. Testing Key Limitations

A useful test suite should verify actual behavior, not just startup configuration.

| Scenario | How to Test | Expectation with Simple Broker |
|---|---|---|
| Subscribed clients | Two clients subscribe to the same destination, then server publishes | All connected clients with matching subscriptions receive the message |
| Offline client | Disconnect one client, publish, then reconnect and subscribe | No historical messages are automatically replayed |
| Application restart | Active subscriptions exist, stop and restart Spring | Clients must reconnect and re-subscribe |
| Sending RECEIPT | Send a frame with a receipt header | Do not rely on the Simple Broker returning RECEIPT |
| ACK | Try using an acknowledgment mode requiring broker support | Do not rely on ACK/redelivery from the Simple Broker |
| Two instances | Clients connect to two different nodes, publish from one node | Do not assume the Simple Broker distributes across nodes |
| Heartbeat | Configure TaskScheduler and heartbeats, then cut network | Verify detection of failed connections; do not treat this as message recovery |
| Large fan-out | Gradually increase sessions, subscribers, message rate, and payload | Measure latency, CPU, heap, GC, and errors instead of assuming a fixed threshold |

With a broker relay, re-run the tests above and add scenarios for broker restarts, broker disconnections, client reconnects, durable subscriptions, and persistence under the specific configuration. A test only proves the broker works in the tested configuration; it does not prove every guarantee exists in the production configuration.

## 16. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Treating Simple Broker like a database | Notification data is lost when the application stops | Store history in a database or event store |
| Expecting offline clients to receive missed messages | Clients miss notifications while disconnected | Provide a history API or use durable queues/subscriptions of an appropriate broker |
| Naming a destination /queue and expecting competing consumers | Multiple matching subscribers can receive the same broadcast | Use an actual queue managed by an external broker |
| Relying on Simple Broker ACK/RECEIPT | Delivery confirmation logic does not work as intended | Switch to a supporting broker or build custom business acknowledgments |
| Running multiple instances while keeping Simple Broker | Subscribers on other nodes are not synchronized | Use a shared broker via STOMP relay |
| Treating heartbeats as delivery guarantees | Connection drops are detected, but messages can still be lost | Design separate persistence, retry, and reconciliation |
| Believing the relay automatically enables durability | Messages can still be non-durable if the broker is not configured | Configure persistent messages and durable queues/subscriptions on the broker |
| Not testing reconnects | Clients can lose subscriptions after a connection drop | Have clients reconnect, resubscribe, and re-sync state |

## 17. Practical Conclusion

The Simple Broker is an in-memory message dispatcher for active subscriptions within the same Spring process. It is convenient for straightforward real-time broadcasts, but does not provide message persistence, durable subscriptions, full ACK/RECEIPT support, or clustering capabilities.

When a system requires delivery guarantees, message storage, background processing, or multi-instance distribution, use a STOMP Broker Relay connected to a dedicated broker. Remember that the relay only forwards messages; persistence, durable queues, retries, ACK, and HA must be supported and configured on the external broker. For critical business data, a database or outbox remains the durable source of guarantees, while WebSocket/STOMP serves as the notification channel to clients.

## References

- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework — STOMP Overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html)
