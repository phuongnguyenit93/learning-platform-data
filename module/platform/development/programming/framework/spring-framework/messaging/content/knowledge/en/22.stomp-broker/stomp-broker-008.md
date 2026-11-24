# Relay Connection Recovery and Delivery Guarantee Limits During Disconnections

## Objectives

When Spring Framework uses the STOMP broker relay to connect to an external broker, network failures can affect the application's system connection, individual TCP connections of WebSocket clients, or the WebSocket connection itself between client and server. Each connection has a different lifecycle and recovery mechanism.

This lesson covers connection topology, heartbeats, automatic relay reconnect, `BrokerAvailabilityEvent`, client reconnect/resubscribe responsibilities, and delivery guarantee limits. The final sections guide you through retries, transactional outbox, idempotency, and failure testing.

## 1. Connections Managed by the Broker Relay

When calling `enableStompBrokerRelay(...)`, Spring forwards STOMP messages between internal message channels and a full-featured broker such as RabbitMQ or ActiveMQ with STOMP enabled.

The relay manages two groups of TCP connections:

| Group | Count | Role |
| --- | --- | --- |
| System connection | One shared connection | Sends messages originating from server-side code to the broker |
| Client connection | One connection per connected WebSocket client | Forwards the client's STOMP frames to the broker and delivers frames from the broker back to the corresponding client |

The system connection is for messages emitted by the server application; it is not used to receive messages sent by the broker to subscribers. Each WebSocket client has its own TCP connection managed by the relay.

~~~text
Spring application
      |
      | brokerChannel
      v
STOMP Broker Relay
      |
      +---- System TCP connection --------> STOMP Broker
      |
      +---- Client TCP connection A <-----> STOMP Broker
      |                 |
      |                 +------------------> WebSocket Client A
      |
      +---- Client TCP connection B <-----> STOMP Broker
                        |
                        +------------------> WebSocket Client B
~~~

Messages from a service via `SimpMessagingTemplate` travel through `brokerChannel` and the system connection. Messages sent by a client via STOMP travel through that session's client connection. This is an important distinction when analyzing reconnects: the relay can automatically recover the system connection, whereas clients must recover their own sessions.

## 2. Relay Configuration and Credentials

Java configuration example:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    private final RelayCredentials credentials;

    public WebSocketConfig(RelayCredentials credentials) {
        this.credentials = credentials;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableStompBrokerRelay("/topic", "/queue")
                .setRelayHost("stomp-broker.internal")
                .setRelayPort(61613)
                .setSystemLogin(credentials.systemLogin())
                .setSystemPasscode(credentials.systemPasscode())
                .setClientLogin(credentials.clientLogin())
                .setClientPasscode(credentials.clientPasscode());

        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

`RelayCredentials` is an application-defined configuration object providing credentials. Place passwords in a secret manager or secure configuration store; never commit passwords to source control.

- `systemLogin` and `systemPasscode` are used for the system connection.
- `clientLogin` and `clientPasscode` are used for TCP connections created on behalf of WebSocket clients.
- The relay always writes its own login/passcode into CONNECT frames forwarded to the broker. STOMP credentials sent by the WebSocket client are ignored. Clients should authenticate via the HTTP handshake and WebSocket endpoint security mechanisms so Spring establishes user identity.
- `/topic` and `/queue` are prefixes forwarded to the external broker; `/app` is for application handlers; `/user` is the user destination prefix resolved by Spring.

## 3. System Connection Heartbeats and Reconnect

The relay sends and receives STOMP heartbeats on the system connection to detect inactive connections. Per Spring Framework documentation, the defaults are:

- Outgoing heartbeat: 10 seconds.
- Incoming heartbeat: 10 seconds.
- When disconnected from the broker, the relay attempts to reconnect the system connection every 5 seconds until successful.

These are default values, not recovery SLAs. Actual failure detection time also depends on heartbeat negotiation, schedulers, networking, TCP timeouts, and broker state.

When the broker comes back online, the relay re-establishes the system connection. The server-side message-sending path can resume operating after the connection is restored.

Reconnecting only restores the connection. It does not automatically store all business messages emitted during the outage, nor does it guarantee automatic redelivery of messages that never reached the broker.

## 4. Tracking Status with `BrokerAvailabilityEvent`

Spring publishes `BrokerAvailabilityEvent` whenever the broker's availability state changes. For the broker relay, the event reflects the system connection being lost or re-established.

Example tracking status with `@EventListener`:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
public class BrokerAvailabilityTracker {

    private final AtomicBoolean available = new AtomicBoolean(false);

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        available.set(event.isBrokerAvailable());
    }

    public boolean isAvailable() {
        return available.get();
    }
}
~~~

`AtomicBoolean` allows threads to read and update the state safely. The initial state is `false`; an event indicating the broker is available flips the flag to `true`, while an unavailable event flips it back to `false`.

Services can check before sending, while still catching send errors:

~~~java
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class UpdatePublisher {

    private final SimpMessagingTemplate messaging;
    private final BrokerAvailabilityTracker availability;

    public UpdatePublisher(
            SimpMessagingTemplate messaging,
            BrokerAvailabilityTracker availability) {
        this.messaging = messaging;
        this.availability = availability;
    }

    public void publish(UpdateEvent event) {
        if (!availability.isAvailable()) {
            throw new IllegalStateException(
                    "STOMP broker is currently unavailable");
        }

        try {
            messaging.convertAndSend("/topic/updates", event);
        }
        catch (MessageDeliveryException exception) {
            // Log and propagate the error to the retry/outbox policy.
            throw exception;
        }
    }
}
~~~

Checking availability avoids some sends when the system connection is already known to be down. However, state can change right after the check, so handling `MessageDeliveryException` must not be omitted.

Limitations of the event:

- Reflects the relay's system connection status, not a health check for individual client connections.
- Does not confirm a specific message was stored by the broker or processed by a client.
- Is not published per message.
- Does not replace retries or durable storage for business data.

## 5. Why Must Clients Reconnect Themselves?

Spring automatically reconnects the relay's system connection. Individual TCP connections for each WebSocket client are not automatically restored into a new STOMP session by that mechanism.

When the broker stops working, clients may lose connectivity. If heartbeats are enabled, clients typically detect an unresponsive broker in around 10 seconds per Spring's description; actual timing depends on configuration and network conditions.

After losing connectivity, the client needs to:

1. Mark the current session as lost.
2. Attempt to reopen the WebSocket/STOMP connection per its retry policy.
3. Wait for STOMP CONNECTED to confirm the new session is ready.
4. Re-send the necessary SUBSCRIBE frames.
5. Sync or request replay of missing data if required by business logic.
6. Handle duplicates using an event ID or business key.

Example with the JavaScript library `@stomp/stompjs`:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "wss://example.com/ws",
    reconnectDelay: 5000,
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000
});

client.onConnect = () => {
    // Callback runs after every successful connection.
    // Register subscriptions here to resubscribe after reconnect.
    client.subscribe("/topic/updates", frame => {
        const event = JSON.parse(frame.body);
        handleUpdate(event);
    });
};

client.onStompError = frame => {
    console.error("STOMP broker error:", frame.headers["message"]);
};

client.activate();
~~~

`reconnectDelay` is a setting on the client library, not a property of the Spring relay. In large systems, consider exponential backoff, a maximum wait cap, and jitter to prevent reconnect storms.

With Spring's Java `WebSocketStompClient`, the application calls `connect(...)` and receives callbacks via `StompSessionHandler`. Upon encountering a transport error or `ConnectionLostException`, client code must schedule a reconnect. Inside the new session's `afterConnected` callback, re-register subscriptions. Do not assume an old `StompSession` revives automatically after the TCP connection is lost.

## 6. Subscriptions and Data During Offline Periods

Subscriptions belong to a STOMP session. When a client reconnects, it gets a new session and must re-send SUBSCRIBE after receiving CONNECTED. Subscriptions from the old session do not automatically transfer to the new session.

A broker may support durable subscriptions, durable queues, or message retention for offline consumers. This capability depends on the broker type, destination configuration, subscription identity, acknowledgment mode, and retention policy. Reconnecting and resubscribing by itself does not guarantee messages broadcast during the offline window will be replayed.

A `/topic/...` destination typically serves active subscribers; it is not inherently a mailbox retaining messages for offline clients. For queues or durable subscriptions, read the broker documentation and verify retention, expiration, consumer identity, and redelivery policies.

## 7. Distinguishing Levels of Send Confirmation

Do not lump every state together as "sent successfully":

| Level | What Can Be Concluded | What Cannot Be Concluded Yet |
| --- | --- | --- |
| `convertAndSend` does not throw | The Spring messaging call did not report a synchronous error | That the client received or processed the message |
| Broker returns `RECEIPT` | The broker/server processed the corresponding frame per STOMP | That consumer-side business logic committed |
| Client receives `MESSAGE` | The frame reached the client connection | That the client application processed it successfully |
| Consumer sends application ACK after processing | The application received confirmation per its custom business protocol | Absence of duplicates if idempotency is missing |

STOMP supports the `receipt` header. A client can ask the broker to return `RECEIPT` after processing SEND or SUBSCRIBE. With Spring's Java STOMP client, `StompSession.setAutoReceipt(true)` automatically adds receipt headers to subsequent operations; or receipts can be set manually in `StompHeaders`. Results are tracked via `Receiptable`. This feature requires a `TaskScheduler` to monitor receipt timeouts.

Example:

~~~java
stompSession.setAutoReceipt(true);

Receiptable receipt = stompSession.send(
        "/topic/updates",
        updateEvent
);

receipt.addReceiptTask(() ->
        log.info("Broker acknowledged the SEND frame"));

receipt.addReceiptLostTask(() ->
        log.warn("Timed out waiting for broker receipt"));
~~~

A receipt confirms processing at the STOMP broker level. It does not replace business acknowledgment from the receiving application. If you need to know the recipient saved an order or completed a task, a separate application-level acknowledgment is required.

`SimpMessagingTemplate.convertAndSend(...)` returns `void`. The method not throwing an exception does not prove a consumer processed the payload. Moreover, Spring's simple broker only supports a subset of STOMP commands and does not support ACK or receipts; those features require a full-featured STOMP-compatible broker.

## 8. Guarantee Limits During Disconnections

Spring's broker relay automatically reconnects the system connection, but does not automatically provide end-to-end or exactly-once business delivery.

### Messages Emitted While the System Connection Is Down

The relay cannot yet forward server-originated messages to the broker over the system connection. The send call may fail with `MessageDeliveryException`. The application must decide whether to return an error, drop, retry, or persist the message for later sending.

### Connection Drops Right When Sending

The application may be unsure whether the broker received the frame. Retrying can produce duplicates if the broker received the message before the connection dropped while the response never reached the application.

### Broker Receives a Message While the Client Is Offline

Whether the message is retained depends on the queue/subscription and broker configuration. Regular topic subscriptions may not retain messages for disconnected clients. Verify durable queues, persistent messages, and the broker's acknowledgment semantics.

### Client Receives Frame but Disconnects Before Finishing Processing

The server does not automatically know whether the client application finished processing. If the application replays messages after reconnect, the consumer may receive duplicates. Consumers need idempotent handling based on an event ID or business key.

### Server Application Restart

Relay reconnect does not replace durable storage inside the application. Critical messages sitting only in memory prior to sending can be lost on process restart. A transactional outbox persists the intent to send within the same business transaction.

## 9. Retries and Transactional Outbox

For critical notifications, store messages to be broadcast in the database before sending. A transactional outbox typically follows this flow:

1. Within the same database transaction, update business data and insert an outbox record.
2. A dispatcher reads unsent records.
3. The dispatcher checks broker availability and attempts to send.
4. Once confirmation matching the required guarantee level is received, mark the record as processed.
5. On transient errors, keep the record to retry with exponential backoff and jitter.
6. Consumers store processed event IDs or use a unique business key to skip duplicate messages.

Example columns in an outbox table:

| Column | Purpose |
| --- | --- |
| `event_id` | Unique ID for deduplication |
| `destination` | STOMP destination |
| `payload` | Serialized message content or reference data |
| `status` | `PENDING`, `IN_PROGRESS`, `SENT`, `FAILED` |
| `attempt_count` | Number of attempts |
| `next_attempt_at` | Next timestamp allowed for retry |
| `created_at` | Event creation timestamp |
| `last_error` | Most recent error |

Do not mark an outbox record `SENT` solely because broker availability is true. Also distinguish a broker receipt from consumer confirmation that business logic committed. Choose the completion point based on the confirmation level the system actually needs.

Retries can cause duplicates when the outcome of a prior send is uncertain. Consumers should enforce a unique constraint on `event_id`; the message-processing transaction records the ID and updates business data atomically.

The outbox, retry, and deduplication pattern generally achieves at-least-once delivery at the application layer. Do not label it exactly-once across the broker, network, client, and database unless a distributed transaction protocol guarantees that.

## 10. Backoff and Load Control

If many clients reconnect simultaneously after an outage, they can create new connections, send CONNECT, and register subscriptions all at once. A reconnect storm can overload the broker right as it recovers.

Retry policies should:

- Start with a short wait and increase gradually using exponential backoff.
- Cap the maximum wait interval.
- Add random jitter to spread out retry attempts.
- Reset backoff after the connection stays stable long enough.
- Avoid spawning multiple reconnect loops for the same client.
- Cap attempts if business rules require transitioning to an intervention-needed state.

Illustrative backoff function example:

~~~java
long delayMillis(int attempt) {
    long base = 1_000L;
    long max = 30_000L;
    int exponent = Math.min(attempt, 5);

    long exponential = Math.min(max, base * (1L << exponent));
    long jitter = ThreadLocalRandom.current()
            .nextLong(0, Math.max(1, exponential / 4));

    return Math.min(max, exponential + jitter);
}
~~~

This is an application retry policy, not the internal reconnect algorithm of the Spring relay.

## 11. Broker Failover and High Availability

By default, the relay reconnects to the same configured host and port. Spring allows customizing the TCP client or supplying dynamic broker addresses to select a different address on each connection attempt.

Example configuration using a custom TCP client:

~~~java
registry.enableStompBrokerRelay("/queue/", "/topic/")
        .setTcpClient(createTcpClient());
~~~

`createTcpClient()` must be implemented according to the project's Spring and Reactor Netty versions. Spring documentation illustrates using `ReactorNettyTcpClient` with an address supplier to choose the connection address.

Being able to pick another broker only solves endpoint discovery. It does not automatically replicate messages, queues, subscriptions, or state across broker nodes. High availability also depends on broker clustering, replication, quorum, persistence, routing, and failover.

If using a virtual host, the relay can set the STOMP `host` header via the `virtualHost` property. This is useful when the physical TCP address differs from the logical host required by the broker.

## 12. Session Monitoring and Event Handling

In addition to `BrokerAvailabilityEvent`, Spring publishes STOMP lifecycle events:

- `SessionConnectEvent`: CONNECT received and client session starting.
- `SessionConnectedEvent`: broker responded with CONNECTED; STOMP session established.
- `SessionSubscribeEvent`: SUBSCRIBE received.
- `SessionUnsubscribeEvent`: UNSUBSCRIBE received.
- `SessionDisconnectEvent`: session ended.

These events can be used to track sessions, users, subscriptions, and connection disruptions. `SessionDisconnectEvent` is sometimes published more than once for the same session, so cleanup logic must be idempotent.

Lifecycle events are not per-message events. If you need to observe or control inbound/outbound messages, use a `ChannelInterceptor` on the appropriate channel and inspect commands/headers via `StompHeaderAccessor` or `SimpMessageHeaderAccessor`.

## 13. Testing Disconnections

An integration test should verify both relay state and client behavior:

1. Start the Spring application and the STOMP broker.
2. Connect a STOMP client, wait for CONNECTED, and register a subscription.
3. Verify messages send and receive normally.
4. Stop the broker or block the TCP path.
5. Verify the application receives the unavailable state via `BrokerAvailabilityEvent`.
6. Call the message-sending service and verify errors are handled properly.
7. Start the broker again.
8. Wait for the relay to publish the available state.
9. Verify the client reconnects, receives CONNECTED, and re-subscribes.
10. Verify messages in the outbox are re-sent according to policy.
11. Re-send the same event ID to verify the consumer does not execute business logic twice.
12. Test dropping the connection immediately after the broker receives a message to evaluate duplicates and retries.

Set clear timeouts for each step; prefer waiting for events or receipts rather than long fixed sleeps. A real broker or STOMP-compatible broker container will more accurately test queue, persistence, and acknowledgment behavior.

## 14. Operational Checklist

- Configure appropriate heartbeats for the system connection and clients.
- Monitor `BrokerAvailabilityEvent` status.
- Catch and classify `MessageDeliveryException`.
- Measure relay reconnect counts, client reconnect counts, and broker unavailable duration.
- Mitigate reconnect storms with backoff and jitter.
- Ensure clients re-subscribe after CONNECTED.
- Decide which destinations require durable queues or persistence.
- Use event IDs and idempotency for consumers.
- Persist critical messages in an outbox before broadcasting.
- Distinguish broker receipts from business acknowledgments.
- Test broker failover and replication.
- Keep `SessionDisconnectEvent` handling logic idempotent.

## 15. Summary

Spring's STOMP broker relay automatically recovers the **system connection** to an external broker: by default it sends/receives heartbeats every 10 seconds and retries connecting every 5 seconds when disconnected. `BrokerAvailabilityEvent` reports changes in the system connection state; message-sending code still needs to handle `MessageDeliveryException`.

Individual TCP connections for WebSocket clients have independent lifecycles. Clients need to reconnect themselves, wait for CONNECTED, and re-register subscriptions. Do not assume messages emitted while offline were retained or will be replayed.

`SimpMessagingTemplate` and the broker relay do not automatically provide exactly-once guarantees for business logic. For critical messages, combine appropriate broker persistence, a transactional outbox, controlled retries, layer-appropriate receipts/acknowledgments, and idempotent consumers.

## References

- [Spring Framework Reference — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework Reference — Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework Reference — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework Reference — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework Javadoc — BrokerAvailabilityEvent](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/broker/BrokerAvailabilityEvent.html)
