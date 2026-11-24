# Comparing Simple Broker and Broker Relay Through Failure Scenarios

## Objectives

After this lesson, you will be able to choose the right broker for Spring WebSocket/STOMP, explain where data and subscriptions live, predict behavior when the application or broker fails, and write integration tests to verify reconnect, heartbeat, message delivery, and subscription recovery.

The focus is on two Spring Messaging configurations:

- **Simple broker:** an in-process STOMP broker built into Spring that stores subscriptions in memory and broadcasts messages to connected clients.
- **Broker relay:** Spring forwards STOMP frames over TCP to an external message broker such as RabbitMQ or ActiveMQ; the external broker manages routing and subscriptions.

Both options share the same WebSocket/STOMP model on the client side and still work with `@MessageMapping`, `SimpMessagingTemplate`, destination prefixes, and Spring Security. The key differences lie in where subscriptions are managed, reliability, scalability, and failure recovery.

## 1. Message Flow in Spring WebSocket/STOMP

STOMP is a frame-based messaging protocol. A client typically opens a WebSocket to a Spring endpoint, then sends frames such as `CONNECT`, `SUBSCRIBE`, `SEND`, `ACK`, and `DISCONNECT`.

Spring routes messages based on destination:

- `/app/**`: routed to `@MessageMapping` methods in the application.
- `/topic/**` and `/queue/**`: typically routed to the broker to handle subscriptions and broadcasting.
- `/user/**`: Spring translates the destination into a per-user/session address.

A typical flow:

1. The browser opens a WebSocket to `/ws`.
2. The client sends STOMP `CONNECT`.
3. The client sends `SUBSCRIBE` to `/topic/orders`.
4. The client or a controller sends a message to `/app/orders`.
5. The `@MessageMapping` method processes it and may send a message to the broker via `SimpMessagingTemplate`.
6. The broker dispatches the message to matching subscriptions; Spring sends frames down to WebSocket clients.

With the simple broker, Spring manages subscriptions and broadcasting itself. With a broker relay, Spring forwards frames over TCP to an external broker and forwards messages returned by the broker down to WebSocket clients.

## 2. What Does the Simple Broker Store and Process?

The simple broker is Spring's built-in broker. It accepts subscribe requests, stores subscription state in memory, and broadcasts messages to connected clients with matching destinations.

Characteristics:

- No external broker installation required.
- Suitable for learning, demos, small apps, or simple broadcast flows.
- Supports path-based destinations and Ant-style patterns.
- Can support STOMP heartbeats if a `TaskScheduler` is configured.
- Supports only a subset of STOMP commands; does not support ACK, RECEIPT, and some advanced broker features.
- Subscriptions live in process memory; there is no durable queue/message store for replay after an application restart.
- Not suitable for multi-instance cluster deployments because subscription state is local to each instance.

The simple broker is not a durable message queue. A destination named `/queue` in a simple broker configuration does not automatically carry the full semantics of a durable queue like RabbitMQ or ActiveMQ.

### Configuring the Simple Broker

Spring Framework example:

~~~java
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
class SimpleBrokerConfig implements WebSocketMessageBrokerConfigurer {

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

The configuration above uses the in-memory broker and enables heartbeats. `TaskScheduler` is obtained from Spring's WebSocket configuration via lazy injection to avoid a circular dependency at startup. You can use the simple broker without configuring heartbeats, but then you must not assume broker heartbeats are active.

## 3. How Does the Broker Relay Work?

The broker relay is a `MessageHandler` in Spring. It receives STOMP messages from internal channels, converts them into frames, and sends them over TCP to an external STOMP broker. Frames coming back from the broker are converted back into Spring messages and sent to the matching WebSocket sessions.

The relay maintains two groups of connections:

1. **System connection:** a single TCP connection used for messages originating from server-side code, such as `SimpMessagingTemplate` called from a REST controller, scheduled task, or service.
2. **Client connections:** a dedicated TCP connection for each WebSocket client connected through Spring.

The system connection is not used to receive all client messages. Each client gets its own connection to send/receive STOMP frames for that session. This lets the broker manage subscriptions and delivery according to STOMP, though it also means broker-side connection count grows with the number of connected clients.

### Configuring the Broker Relay

Example with RabbitMQ with the STOMP plugin enabled, or a compatible STOMP broker:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.messaging.simp.config.StompBrokerRelayRegistration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompRelayConfig implements WebSocketMessageBrokerConfigurer {

    private final Environment environment;

    StompRelayConfig(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        StompBrokerRelayRegistration relay =
            registry.enableStompBrokerRelay("/topic", "/queue");

        relay.setRelayHost(environment.getRequiredProperty("stomp.relay.host"));
        relay.setRelayPort(environment.getRequiredProperty(
            "stomp.relay.port", Integer.class));

        relay.setClientLogin(environment.getRequiredProperty(
            "stomp.relay.client-login"));
        relay.setClientPasscode(environment.getRequiredProperty(
            "stomp.relay.client-passcode"));

        relay.setSystemLogin(environment.getRequiredProperty(
            "stomp.relay.system-login"));
        relay.setSystemPasscode(environment.getRequiredProperty(
            "stomp.relay.system-passcode"));

        relay.setSystemHeartbeatSendInterval(10_000);
        relay.setSystemHeartbeatReceiveInterval(10_000);
    }
}
~~~

Login properties must be injected from a secret manager or environment secret store. Do not write real passwords into source code or commit configuration files containing secrets.

With a relay, STOMP support must be installed and enabled on the broker. If using RabbitMQ, the STOMP plugin must be enabled; its default TCP listener port is `61613`. The default AMQP port `5672` is not the STOMP listener port. Example enabling the plugin:

~~~bash
rabbitmq-plugins enable rabbitmq_stomp
~~~

## 4. Comparing Architecture and Failure Boundaries

| Aspect | Simple broker | Broker relay |
|---|---|---|
| Where subscriptions live | Spring application memory | External broker |
| Where routing/broadcast happens | Simple broker inside JVM | STOMP broker over TCP |
| Message persistence | No built-in durable message store | Depends on broker, destination, delivery mode, and policy |
| STOMP ACK/RECEIPT | Not fully supported | Relay forwards features supported by the broker |
| Heartbeat | Supported if scheduler is configured | Active on system connection; client sessions also need matching heartbeats |
| Broker reconnect | No external broker to reconnect to | Relay automatically reconnects the system connection |
| Client reconnect | Client must reopen WebSocket/STOMP after session loss | Client must still reconnect itself; relay does not restore client sessions |
| Clustering | Does not share subscriptions across JVMs | Multiple Spring instances can relay to the same broker |
| Operations | Few components, simple | Must operate broker, STOMP listener, credentials, storage, and monitoring |
| Best fit | Demos, simple broadcasts, few instances | Production needing an independent broker, multiple instances, broker features, and backlog management |

The broker relay does not automatically make all messages durable. For messages to survive broker restarts, you must configure durable destinations/subscriptions, persistent delivery, and storage per the broker's semantics. Especially with topics, temporary subscriptions may be lost on client disconnect; if offline clients need a backlog, choose durable subscriptions/queues or a broker-specific event storage mechanism.

## 5. Failure Scenario 1: External Broker Stops or Restarts

This scenario applies only to the broker relay because the simple broker does not depend on an external broker process.

### With the Simple Broker

While the Spring application remains running, the simple broker is still considered available. There is no external broker to detect restarts or reconnect to. Messages continue to be broadcast within the WebSocket sessions connected to that instance.

If the Spring application itself stops, the simple broker stops with it. All in-memory subscriptions are lost; when the application restarts, clients must reconnect and re-subscribe.

### With the Broker Relay

When the external broker disconnects:

1. The relay's system TCP connection drops.
2. Spring publishes `BrokerAvailabilityEvent` to indicate the broker is unavailable.
3. The relay keeps attempting to reconnect the system connection; by default it retries every 5 seconds.
4. Once the connection is re-established, Spring publishes an available event.
5. Messages sent from the server while the broker is unavailable may fail; code must check state and handle `MessageDeliveryException`.

Key point: the relay automatically reconnects the **system connection**, yet individual WebSocket client connections are not automatically restored. When the broker restarts, clients typically detect the failure via heartbeats (Spring docs note around 10 seconds under default heartbeat settings) and must reconnect and re-subscribe on their own.

Do not conclude that because the broker has recovered, every browser subscription has recovered as well. The two have different lifecycles.

## 6. Failure Scenario 2: Spring Application Restarts or Crashes

| Symptom | Simple broker | Broker relay |
|---|---|---|
| WebSocket session | Lost when app process stops | Lost when app process stops |
| Subscription | Completely lost since it resides in the JVM | Client connection closes; broker handles subscription per connection and durable policy |
| Messages sent before crash | No store for replay | Only retained if the broker already received them and destination/persistence policies allow |
| Client after restart | Opens new WebSocket and re-subscribes | Opens new WebSocket/STOMP and re-subscribes |
| Server-side publisher | Works only while app runs | New system connection is created by the relay when app starts |

The broker relay preserves broker-owned messages better across Spring application restarts, but WebSocket sessions still belong to the Spring application. Clients are not automatically reattached to old sessions just because the broker stayed alive.

If messages missed while a client was offline must be recovered:
- Use durable queues/subscriptions supported by the broker.
- Or store events in a database/event store with a sequence/cursor.
- Have the client send its last-seen offset after reconnecting so the server replays the missing range.
- Use event IDs so clients deduplicate during replay.

## 7. Failure Scenario 3: Network Partition Between Spring and Broker

A network partition can prevent the application from reaching the broker even though the broker process is still running. From the relay's perspective, behavior closely resembles a broker restart:

- Heartbeats on the system connection detect the connection is no longer active.
- The relay publishes an unavailable state and attempts to reconnect.
- When the network recovers, the relay reconnects the system connection.
- Client connections must be observed separately; do not assume the system connection state represents all client connections.

Asymmetric states can occur: the system connection has reconnected while a WebSocket client still holds a stale session or has not received a heartbeat yet. Therefore, clients must manage reconnect and resubscribe independently.

Do not use a single `brokerAvailable=true` flag to assert that all clients are connected. Broker status and individual WebSocket session status are two separate dimensions.

## 8. BrokerAvailabilityEvent and Handling Message Sends When Broker Is Unavailable

Spring publishes `BrokerAvailabilityEvent` when broker availability changes. With the simple broker, the broker is considered available as soon as the application starts and stays available while the application runs. With the broker relay, the event reflects the state of the system connection to the external broker.

Example tracking availability:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
class BrokerAvailabilityMonitor {

    private final AtomicBoolean available = new AtomicBoolean();

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        available.set(event.isBrokerAvailable());
    }

    public boolean isAvailable() {
        return available.get();
    }
}
~~~

A service can check before broadcasting:

~~~java
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderBroadcastService {

    private final SimpMessagingTemplate messagingTemplate;
    private final BrokerAvailabilityMonitor brokerMonitor;

    OrderBroadcastService(
            SimpMessagingTemplate messagingTemplate,
            BrokerAvailabilityMonitor brokerMonitor) {
        this.messagingTemplate = messagingTemplate;
        this.brokerMonitor = brokerMonitor;
    }

    public void broadcast(OrderUpdate update) {
        if (!brokerMonitor.isAvailable()) {
            throw new IllegalStateException("STOMP broker is unavailable");
        }

        try {
            messagingTemplate.convertAndSend("/topic/orders", update);
        }
        catch (MessageDeliveryException ex) {
            // Log the error and hand off to an appropriate persistence/retry mechanism.
            throw ex;
        }
    }
}
~~~

This is an illustrative example; the monitor must be initialized according to the application lifecycle and callers must handle exceptions appropriately. Checking availability is only a guard and does not eliminate race conditions: the broker can lose connectivity right after the check. Therefore, still catch `MessageDeliveryException`.

Do not automatically retry business messages infinitely right inside the request thread. If a message must be resent after an outage, persist the event to a transactional outbox or durable queue and let a dedicated publisher resend it. Attach a stable event ID to avoid duplicates if the broker already received the message before the client received confirmation.

## 9. Client Recovery: Reconnect and Resubscribe

A STOMP client needs an explicit state machine:

1. **CONNECTED:** WebSocket is open and STOMP `CONNECTED` has been received.
2. **DISCONNECTED:** WebSocket closed or heartbeat timed out.
3. **RECONNECTING:** wait for backoff, then open a new WebSocket/STOMP session.
4. **RESUBSCRIBING:** after receiving `CONNECTED`, re-register all required destinations.
5. **SYNCHRONIZING:** send last-seen event ID/offset to fetch missed data if the system supports replay.
6. **CONNECTED:** resume real-time processing.

Recommendations:
- Use exponential backoff with jitter so many clients do not reconnect simultaneously the moment the broker recovers.
- Limit attempt counts or show a clear offline state during prolonged outages.
- Refresh access tokens before reconnecting if the login session has expired.
- Re-subscribe after STOMP `CONNECTED`, not immediately when the raw WebSocket TCP connection opens.
- Use fresh subscription IDs for the new session and manage callbacks by lifecycle.
- Do not assume messages sent while offline will be backfilled automatically.
- Use sequence numbers/cursors or event IDs if gap detection and deduplication are needed.

With a relay, heartbeats between the relay and the broker do not replace heartbeats between the browser and the Spring WebSocket endpoint. Both links must be monitored separately.

## 10. Failure Scenario 4: Message Sent Right as the Broker Disconnects

This scenario has the most uncertain outcome.

Example:
1. The service calls `SimpMessagingTemplate.convertAndSend(...)`.
2. The relay begins writing the STOMP frame to TCP.
3. The network drops before the application receives a response.
4. The caller does not know whether the broker received the message.

Resending an event with side effects may create duplicates. Not resending may lose the message.

How to handle:
- For real-time notifications where occasional loss is acceptable, log/record metrics and rely on the client resyncing state on reconnect.
- For critical business events, write to an outbox in the same transaction as business data.
- A publisher reads the outbox and resends to the broker until appropriate confirmation is received.
- Consumers use an inbox/unique constraint for idempotent processing.
- If the broker supports STOMP RECEIPT/ACK, use them per the broker's semantics; a receipt does not inherently mean a consumer finished processing.

The simple broker does not support STOMP ACK/RECEIPT like a full broker. The broker relay forwards features supported by the external broker, though final guarantees still depend on the broker, destination, and persistence configuration.

## 11. Failure Scenario 5: Running Multiple Spring Application Instances

With the simple broker, each JVM holds its own subscription set. Client A connects to instance 1, client B connects to instance 2; if a message is broadcast inside instance 1's simple broker, client B does not receive it automatically just by subscribing to the same destination on instance 2.

With a broker relay, Spring instances can all connect to one external broker. The broker manages routing/subscriptions centrally, so messages from instance 1 can be delivered to clients connected through instance 2, provided broker topology and STOMP destinations are configured properly.

However, the broker relay does not solve every clustering concern:
- Each instance still holds its own WebSocket sessions.
- The user destination registry is local; if using `/user/**` across multiple instances, configure appropriate broadcast/registry sharing.
- The load balancer still needs proper WebSocket upgrade, timeout, and distribution settings.
- Each WebSocket client opens a TCP connection to the broker via the relay; account for connection limits and broker resources.
- The broker becomes critical infrastructure requiring HA, monitoring, capacity planning, and backups.

## 12. Heartbeats, Timeouts, and Failure Detection

Heartbeats are periodic frames/traffic helping both sides detect abnormally silent connections. They are not a mechanism to guarantee message storage or processing.

With the broker relay:
- The system connection sends and receives heartbeats every 10 seconds by default.
- If disconnected from the broker, the relay attempts to reconnect every 5 seconds by default.
- STOMP client heartbeats must be configured and negotiated separately.
- Clients typically detect an unresponsive broker within about 10 seconds when heartbeats are enabled, though exact timing depends on heartbeat negotiation, network timeouts, and client libraries.

With the simple broker:
- A `TaskScheduler` must be configured to send/receive STOMP heartbeats.
- Heartbeats help detect inactive WebSocket/STOMP sessions.
- They do not turn the simple broker into a durable or clustered broker.

Do not set heartbeats too short if the network has jitter or clients run on mobile devices. Overly sensitive timeouts can trigger reconnect storms; overly long timeouts delay failure detection. Measure RTT and network behavior in a real environment to choose values.

## 13. ACK, RECEIPT, and Durability Depend on the Broker

The simple broker supports only a subset of STOMP commands and does not support ACK/RECEIPT. The broker relay forwards frames to an external broker, so ACK, NACK, RECEIPT, persistence, and durable subscription capabilities depend on the broker's STOMP implementation.

RabbitMQ example:
- Requires enabling the `rabbitmq_stomp` plugin.
- The plugin supports STOMP 1.0, 1.1, and 1.2 along with certain extensions.
- Subscriptions can use `auto`, `client`, and `client-individual` acknowledgement modes.
- Persistent messages can be requested using the `persistent:true` header.
- `NACK`, requeue, and dead-letter semantics depend on broker configuration.

Do not generalize RabbitMQ behavior to ActiveMQ or other brokers. When switching brokers, re-run contract/integration tests for ACK, RECEIPT, durable subscriptions, queue naming, and dead-letter policies.

## 14. Testing with Failure Injection

Unit tests can verify event handling logic and `BrokerAvailabilityEvent` listeners, but they are not enough to prove TCP reconnects, heartbeats, STOMP sessions, or broker persistence. Those behaviors require integration tests with a real broker.

### Test Matrix

| Scenario | Simple broker config | Broker relay config | Key assertion |
|---|---|---|---|
| Spring app restart | In-JVM subscriptions lost | WebSocket sessions lost; external broker stays up | Clients reconnect and re-subscribe |
| Broker restart | No external broker applicable | System connection unavailable then reconnects | Unavailable/available events fire; relay recovers |
| Network partition | Test per-WebSocket/instance | System connection drops; relay retries | Clients reconnect and resubscribe independently |
| Send while broker unavailable | Simple broker stays active while app lives | May throw MessageDeliveryException | Caller does not assume message was persisted |
| Client disconnect | Client subscription/session ends | Client TCP connection ends | Session cleanup is idempotent |
| Two app instances | Subscriptions not shared | Same broker delivers cross-instance messages | Clients on both instances receive events |
| ACK/RECEIPT | Not fully supported | Per broker STOMP implementation | Verify exact provider semantics |
| Broker message retention | No durable store | Per persistent delivery/durable destination | Offline messages received on reconnect if configured |

### Using RabbitMQ as the Test Broker

An integration test with RabbitMQ requires:
1. Start a RabbitMQ container or dedicated test broker.
2. Enable the STOMP plugin via `rabbitmq-plugins enable rabbitmq_stomp`.
3. Expose the STOMP TCP port (default 61613).
4. Start the Spring application with `enableStompBrokerRelay`.
5. Connect two STOMP clients and subscribe to a shared destination.
6. Send a message from a client or `SimpMessagingTemplate`, verify clients receive it.
7. Stop the broker and wait for `BrokerAvailabilityEvent(false)`.
8. Restart the broker and wait for the relay to reconnect and emit `BrokerAvailabilityEvent(true)`.
9. Verify browsers/clients reconnect and re-subscribe automatically; do not check only the system connection.
10. If testing offline message retention, create durable destinations/subscriptions per RabbitMQ STOMP semantics and verify the backlog.

You can use Testcontainers for broker lifecycle and Toxiproxy or network rules to inject partitions. Use latches, Awaitility, or polling with timeouts instead of fixed `Thread.sleep`.

### Key Assertions

- The simple broker does not lose subscriptions when only an external broker stops, because there is no external broker in that architecture.
- When the Spring process stops, the simple broker loses subscription state.
- The relay publishes `BrokerAvailabilityEvent` when the system connection changes state.
- The relay system connection reconnects; client sessions still require independent reconnection.
- Clients must send `SUBSCRIBE` again after reconnecting.
- Messages sent during an outage must have a clear handled outcome: retry/outbox, intentional drop, or cursor resync.
- Disconnect events can fire multiple times; cleanup logic must be idempotent.
- Durable messages/subscriptions are verified only when the broker actually stores and replays them under the chosen configuration.

## 15. Production Observability and Operations

Track separate signals:

**In the Spring application**
- `BrokerAvailabilityEvent` state.
- Connected/disconnected WebSocket session counts.
- STOMP CONNECT/SUBSCRIBE/DISCONNECT counts.
- `MessageDeliveryException` count.
- Client reconnect and resubscribe counts.
- Message channel latency and rejected message count.

**In the external broker**
- TCP/STOMP connection count.
- Subscription/consumer count.
- Queue depth and ready/unacknowledged message counts if supported by the broker.
- Publish/consume rates.
- Redelivery, ACK/NACK, and DLQ metrics.
- Disk/memory watermarks and cluster health.

Logs should include WebSocket session ID, authenticated user ID, destination, correlation/event ID, and connection state. Avoid logging tokens, passcodes, or full sensitive payloads.

With a broker relay, each client holds a separate TCP connection to the broker; capacity-plan for concurrent clients, heartbeats, connection limits, file descriptors, and network bandwidth. With the simple broker, capacity lives inside the Spring application JVM and depends on subscription count, WebSocket session count, message size, and outbound throughput.

## 16. Security When Using Broker Relay

The Spring broker relay configures STOMP `login` and `passcode` for connections it opens to the broker. The relay always puts these headers into the CONNECT frame sent on the client's behalf; login/passcode values sent by the browser in STOMP CONNECT are ignored.

Therefore:
- Protect the WebSocket endpoint with HTTP authentication and TLS.
- Use Spring Security to authenticate users and authorize destinations/messages.
- Use separate broker accounts for the system connection and client connections; grant only necessary permissions.
- Store credentials in a secret manager.
- Never expose system credentials to browsers.
- Restrict subscriptions to private destinations and `/user/**`.
- Test that users cannot subscribe/send to another user's destinations.

Broker authentication does not replace application-layer authorization. If all browser connections share a single broker credential through the relay, the broker may see only one service identity; Spring still must enforce access control per authenticated user.

## 17. Choosing Simple Broker vs. Broker Relay

| Requirement | Suitable choice |
|---|---|
| Demos, learning STOMP, simple broadcasts | Simple broker |
| Single Spring instance, no ACK/RECEIPT required | Simple broker can be used |
| Multiple Spring instances publishing/receiving real-time updates | Broker relay |
| Need broker queues, durable subscriptions, ACK/NACK | Broker relay with a broker supporting those features |
| Need messages to survive while clients are offline | Broker relay + durable destinations/subscriptions or event store |
| Need backlog management, DLQ, and broker monitoring | Broker relay |
| Want minimal operational components and accept in-memory state | Simple broker |
| Need independent scaling between WebSocket app and messaging | Broker relay |

A broker relay improves scalability and provides broker features, yet adds infrastructure to deploy, secure, back up, and monitor. Choose a relay when reliability, clustering, or backlog requirements genuinely call for it; do not choose it merely because of the label "production".

## 18. Common Mistakes

- **Assuming the relay reconnects all browsers:** the relay reconnects the system connection; client sessions must be recovered by the client.
- **Waiting only on BrokerAvailabilityEvent and assuming all clients are online:** the event reflects the system connection, not individual WebSocket client states.
- **Assuming the simple broker has durable queues:** subscription and broadcast state live in JVM memory.
- **Assuming the broker relay guarantees zero message loss by itself:** you must configure persistence, destinations, ACK/RECEIPT, and broker storage.
- **Sending messages while the broker is unavailable without catching exceptions:** the server can throw MessageDeliveryException.
- **Automatically retrying every message without an event ID:** can create duplicates if the broker already received the message before the connection dropped.
- **Reconnecting WebSocket without re-subscribing:** a new STOMP session does not automatically restore old subscriptions.
- **Using ACK/RECEIPT with the simple broker:** the simple broker does not fully support these commands.
- **Using the broker relay without enabling the STOMP plugin:** TCP connections to the STOMP port will fail even while the AMQP port works.
- **Using default guest/guest credentials in production:** creates access risks and is often restricted by host/provider.
- **Using the simple broker across multiple instances expecting cross-node broadcasts:** each JVM maintains separate subscriptions.
- **Not handling duplicate SessionDisconnectEvent:** cleanup may run multiple times and corrupt state.

## 19. Pre-Release Checklist

- [ ] Chosen simple broker or broker relay based on reliability and scale requirements.
- [ ] If using a relay, broker has STOMP listener enabled on the correct host/port.
- [ ] System/client credentials configured via secret store.
- [ ] Appropriate heartbeats enabled on both relay and STOMP clients.
- [ ] Handled `BrokerAvailabilityEvent` and `MessageDeliveryException`.
- [ ] Clients reconnect, re-authenticate, and resubscribe after STOMP CONNECTED.
- [ ] Event IDs/cursors exist if gap detection and deduplication are needed.
- [ ] Verified durable subscriptions/persistent messages against the actual broker.
- [ ] Tested broker restarts and network partitions.
- [ ] Tested Spring app restarts and client reconnects.
- [ ] Tested multiple Spring instances if deploying as a cluster.
- [ ] Verified ACK/RECEIPT per the broker's STOMP implementation.
- [ ] Metrics exist for broker availability, session count, reconnects, queue depth, and DLQ.
- [ ] Protected WebSocket endpoints and destination-level authorization.
- [ ] Capacity-planned TCP connections, heartbeats, and broker resources.

## References

- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html): in-memory subscriptions, destination patterns, and heartbeats.
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html): simple broker limitations and broker relay configuration.
- [Spring Framework — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html): system/client TCP connections, credentials, heartbeats, and reconnect intervals.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html): BrokerAvailabilityEvent, session lifecycle events, and client reconnect behavior.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): message channels and flows when using simple broker or broker relay.
- [Spring Framework — BrokerAvailabilityEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/broker/BrokerAvailabilityEvent.html): `isBrokerAvailable()` and event semantics.
- [RabbitMQ — STOMP Plugin](https://www.rabbitmq.com/docs/stomp): enabling the STOMP plugin, listener port, ACK/NACK, and persistent messages.
