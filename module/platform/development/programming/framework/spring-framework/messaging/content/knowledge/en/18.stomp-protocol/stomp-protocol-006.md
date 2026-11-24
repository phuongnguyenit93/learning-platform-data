# Heart-beat and detecting inactive connections in STOMP

## 1. Why do long-lived connections need a heartbeat?

WebSocket keeps a TCP connection open for a long time so that the client and server can send data in both directions. A connection can still exist in the application's state table even though the network path in between is broken. For example:

- A laptop switches from Wi-Fi to a mobile network.
- The browser goes to sleep, or a background tab has its timers limited by the operating system.
- A router or firewall drops the NAT state of an idle connection.
- A reverse proxy closes the socket because of an idle timeout.
- The broker restarts or loses its connection to the application.
- One side hangs and no longer reads or writes data.

TCP does not always notify you immediately when a path is silently cut. If no data passes through, the application can hold on to a stale session for a very long time. This makes the count of online clients wrong, keeps subscriptions that no longer have a receiver, holds resources, and causes attempts to send messages to the stale session to fail continuously.

A heartbeat is a small piece of data sent periodically when the connection has no business traffic. When one side stops receiving heartbeats within the allowed time, the other side can mark the connection as inactive and close or remove the session.

A heartbeat helps check the liveness of the connection. It does not confirm that the user is still looking at the screen, does not confirm that the business has processed a message, and does not replace STOMP's ACK/RECEIPT.

## 2. At which layer does the heartbeat sit?

You need to distinguish three common mechanisms:

| Mechanism | Layer | Data sent | Purpose |
|---|---|---|---|
| TCP keepalive | TCP/OS | TCP probe | Detects a peer or TCP path that is not responding |
| WebSocket Ping/Pong | WebSocket | Ping and Pong control frames | Checks the WebSocket connection |
| STOMP heart-beat | STOMP | A single EOL character, usually LF | Checks the activity of the STOMP peer and broker |

STOMP heartbeat is data at the application layer. If there is no business STOMP frame to send, the sender sends a blank line (an EOL, usually the LF byte). If other STOMP data has already passed through, that data also counts as activity and no additional heartbeat needs to be sent within that interval.

WebSocket Ping/Pong are control frames of the WebSocket protocol. The browser WebSocket API does not provide a JavaScript method for an application to send a Ping control frame itself; the runtime and the WebSocket implementation handle these control frames. Therefore, browser applications that use STOMP usually rely on STOMP heartbeat to monitor activity at the messaging layer.

TCP keepalive can be useful at the network layer, but the default time depends on the operating system and the server configuration. You should not treat TCP keepalive as a STOMP business timeout.

## 3. STOMP 1.1/1.2 negotiates heartbeat

STOMP has supported heartbeat since version 1.1. The two sides exchange their ability to send and their need to receive right at the start of the session:

- The client sends the heart-beat header in the CONNECT frame.
- The server returns the heart-beat header in the CONNECTED frame.

Each header has two non-negative integers, in milliseconds:

**heart-beat: can-send, want-receive**

The first number describes the smallest interval the sender can guarantee between two outgoing heartbeats. A value of 0 means that side cannot send heartbeats.

The second number describes the interval at which the sender wants to receive heartbeats from the peer. A value of 0 means it does not require receiving heartbeats.

Example the client sends:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
heart-beat:10000,15000

^@
~~~

The server returns:

~~~text
CONNECTED
version:1.2
heart-beat:5000,20000

^@
~~~

Here:

- The client can send heartbeats at least every 10,000 ms and wants the server to send within 15,000 ms.
- The server can send heartbeats at least every 5,000 ms and wants the client to send within 20,000 ms.

If the heart-beat header does not appear, STOMP treats it as heart-beat:0,0. When a value of 0 makes a direction impossible to negotiate, that direction has no heartbeat.

### 3.1. The negotiation formula

Notation:

- **cx**: the client can send heartbeats.
- **cy**: the client wants to receive heartbeats.
- **sx**: the server can send heartbeats.
- **sy**: the server wants to receive heartbeats.

The heartbeat interval from client to server:

**client → server = max(cx, sy)**

There is a heartbeat only if cx is greater than 0 and sy is greater than 0. If either is 0, the client-to-server direction is disabled.

The heartbeat interval from server to client:

**server → client = max(sx, cy)**

There is a heartbeat only if sx is greater than 0 and cy is greater than 0. If either is 0, the server-to-client direction is disabled.

With the example above:

| Direction | Calculation | Heartbeat interval |
|---|---|---:|
| Client → Server | max(10,000, 20,000) | 20,000 ms |
| Server → Client | max(5,000, 15,000) | 15,000 ms |

The max value is used because the sender only commits to sending according to its own capability, while the receiver only states the maximum frequency at which it wants to receive. The two sides must choose an interval that satisfies both conditions.

### 3.2. A heartbeat is an EOL, not a business STOMP frame

When there is no business frame to send within the negotiated interval, the sender sends an EOL (end-of-line). In STOMP 1.2, the EOL is LF or CRLF; an ordinary heartbeat is a single LF.

A heartbeat has no command, headers, body, or the NULL terminator of a business frame. It only keeps the STOMP stream carrying new data so that the peer knows the connection is still active.

STOMP specifies that any newly received data on the connection can prove that the peer is active. Therefore, if the client continuously sends SEND, SUBSCRIBE, or other STOMP frames, those frames also refresh the data-receipt state.

## 4. When is a connection considered inactive?

Suppose the two sides have negotiated a heartbeat interval of n milliseconds for one direction. The sender must send new data at least every n milliseconds. If no STOMP frame needs to be sent, the sender must send an EOL.

The receiver can consider the connection dead if it receives no new data for a period of at least n. The STOMP specification requires the receiver to allow a time error margin because timers, scheduling, the network, and system load can make a heartbeat arrive late.

There is no single timeout factor required for every broker and every client. Each implementation can choose its own grace period:

- The Spring simple broker uses a factor of 3 for the client heartbeat read timeout.
- STOMP.js has heartbeatToleranceMultiplier; the current documentation defaults it to 2.
- An external broker can have its own timeout or grace period.

Do not use exactly one heartbeat interval as a hard timeout if the environment has jitter or browser background timers. A timeout that is too short creates false disconnects; a timeout that is too long causes dead sessions to be cleaned up slowly.

## 5. Enabling heartbeat for the Spring simple broker

The Spring simple broker can send heartbeats and detect that a client no longer sends data. You need to provide a TaskScheduler to run the heartbeat task.

Spring Framework 6.2 example:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompHeartbeatConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Bean
    ThreadPoolTaskScheduler stompHeartbeatScheduler() {
        ThreadPoolTaskScheduler scheduler =
            new ThreadPoolTaskScheduler();

        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue")
            .setHeartbeatValue(new long[] {10_000, 10_000})
            .setTaskScheduler(stompHeartbeatScheduler());

        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

In setHeartbeatValue:

- The first element is the interval at which the server sends heartbeats when there is no outbound data.
- The second element is the interval at which the server wants the client to send heartbeats.
- The unit is milliseconds.
- A value of 0 disables heartbeat in the corresponding direction.

When setTaskScheduler is called without setting a heartbeat value, the Spring simple broker defaults to [10000, 10000]. The example above sets both values explicitly so that the configuration is easy to read and operate.

If you configure a heartbeat other than [0,0] without providing a TaskScheduler, the simple broker cannot run the heartbeat task and will report an error at startup. When you do not need heartbeat, you can keep the value [0,0] and not configure a scheduler for the broker.

ThreadPoolTaskScheduler is a Spring bean, so Spring manages its startup and shutdown lifecycle. Use a dedicated scheduler for heartbeat so that threads are easy to observe and so that the application's blocking work is not attached to this scheduler.

## 6. How does the Spring simple broker detect a dead client?

When it receives CONNECT, the simple broker reads the heartbeat the client declared and the server-side heartbeat value. The broker stores:

- The session ID and the Principal.
- The channel used to send data to the WebSocket session.
- The interval to wait for data from the client.
- The interval at which to send data to the client.
- The time of the most recent receive and send.

Every inbound message that has a session ID updates the most recent read time. Therefore, a valid business message also refreshes liveness; the broker is not required to receive a separate LF character if the client has sent other STOMP data.

If the client → server interval has been negotiated, the Spring simple broker uses:

**read timeout = 3 × max(client can-send, server wants-receive)**

The factor of 3 is the grace period in the Spring simple broker implementation, consistent with the STOMP specification's requirement to allow an error margin. This is the behavior of the Spring simple broker, not a factor required of every STOMP broker.

When the heartbeat task detects that the time with no inbound data exceeds the read timeout, the broker:

1. Removes the session from the simple broker's list of active sessions.
2. Cancels all subscriptions belonging to that session.
3. Sends a DISCONNECT_ACK notification toward the WebSocket messaging infrastructure to end the session.

In the outbound direction, the broker sends a heartbeat when there is no data to send to the client within the negotiated interval. If there is an outbound message, that message also refreshes the most recent write time.

This detection only works if the two sides have negotiated heartbeat for the direction to be monitored. If the client sends heart-beat:0,0, or the server sets the corresponding receive value to 0, the simple broker has no read timeout for that direction.

## 7. Using STOMP.js in the browser

With a browser client using @stomp/stompjs, two important properties are:

- heartbeatOutgoing: the interval at which the client wants to send heartbeats to the server.
- heartbeatIncoming: the interval at which the client wants to receive heartbeats from the server.

Example:

~~~javascript
import { Client, TickerStrategy } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    heartbeatOutgoing: 10_000,
    heartbeatIncoming: 10_000,
    reconnectDelay: 5_000,

    onConnect: () => {
        console.log("STOMP connected");

        // onConnect runs again after every reconnect.
        client.subscribe("/topic/presence", (frame) => {
            console.log("presence:", frame.body);
        });
    },

    onWebSocketClose: (event) => {
        console.warn("WebSocket closed:", event.code, event.reason);
    },

    onStompError: (frame) => {
        console.error("STOMP error:", frame.headers["message"]);
    }
});

// The Worker strategy makes the heartbeat timer less subject to throttling
// when the browser tab runs in the background, if the environment supports Web Workers.
client.heartbeatStrategy = TickerStrategy.Worker;

// Available in newer STOMP.js versions (7.5+).
client.onHeartbeatLost = () => {
    console.warn("No heartbeat received from STOMP server");
};

client.activate();
~~~

heartbeatOutgoing and heartbeatIncoming are the values the client announces in CONNECT. The actual interval is still negotiated with the server according to the STOMP 1.2 formula.

If heartbeatIncoming or heartbeatOutgoing is 0, the client disables the corresponding direction. Do not set a value that is too small when there is no specific requirement: heartbeat creates traffic, timers, and processing work on both the client and the server.

STOMP.js supports automatic reconnect through reconnectDelay. When the reconnect succeeds, the onConnect callback runs again; re-register subscriptions there. A reconnect only restores the transport and a new STOMP session; it does not automatically restore business state or the messages that were missed.

### 7.1. Background browser tabs and limited timers

A browser can reduce timer frequency when a tab is in the background or the device switches to power-saving mode. A client that uses ordinary timers may send heartbeats later than expected and be considered by the server as having lost the connection.

With a STOMP.js version that supports it, you can use TickerStrategy.Worker to send heartbeats via a Web Worker. This reduces the impact of timer throttling in a background tab, but does not guarantee that the connection always stays alive when the machine sleeps or the network is cut.

If the client is closed or the device sleeps, heartbeat cannot replace the reconnect and state recovery procedure after activity resumes.

## 8. A Java client with WebSocketStompClient

Spring provides WebSocketStompClient for Java applications that need to connect to a STOMP endpoint over WebSocket.

The client needs a TaskScheduler for heartbeat scheduling and receipt tracking:

~~~java
@Bean
ThreadPoolTaskScheduler stompClientTaskScheduler() {
    ThreadPoolTaskScheduler scheduler =
        new ThreadPoolTaskScheduler();

    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("stomp-client-");
    return scheduler;
}

@Bean
WebSocketStompClient webSocketStompClient(
        ThreadPoolTaskScheduler stompClientTaskScheduler) {

    WebSocketStompClient client =
        new WebSocketStompClient(new StandardWebSocketClient());

    client.setTaskScheduler(stompClientTaskScheduler);
    client.setDefaultHeartbeat(new long[] {10_000, 10_000});

    return client;
}
~~~

The first value of setDefaultHeartbeat is the interval at which the client sends heartbeats; the second value is the interval at which the client wants the server to send. When a scheduler is present, the Spring STOMP client defaults to preferring [10000,10000]; the example still sets it explicitly to avoid depending on the default.

WebSocketStompClient only sends a heartbeat when no other message is being sent. If you are sending messages continuously, that data counts as activity. The scheduler also supports tracking the deadline of a RECEIPT if the application uses receipt tracking.

With code that uses the Spring STOMP client and an external broker relay, note that messages sent to a destination handled internally such as /app/... may not be relayed to the broker. The broker may therefore not see the data the client sends and may consider the connection idle. Configuring a TaskScheduler on the broker relay helps Spring track client activity and send heartbeats to the broker when needed.

## 9. Heartbeat with an external STOMP broker relay

When using enableStompBrokerRelay, Spring maintains two kinds of connections to the external broker:

- One system TCP connection used for messages sent by the server application.
- A separate TCP connection for each connected WebSocket client.

The system connection has its own heartbeat. Spring Framework by default sends and waits for a heartbeat from the broker every 10 seconds. If the system connection is lost, the broker relay automatically tries to reconnect, by default every 5 seconds.

Configuration example:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableStompBrokerRelay("/topic", "/queue")
        .setRelayHost("broker.example.com")
        .setRelayPort(61613)
        .setSystemHeartbeatSendInterval(10_000)
        .setSystemHeartbeatReceiveInterval(10_000);

    registry.setApplicationDestinationPrefixes("/app");
}
~~~

setSystemHeartbeatSendInterval and setSystemHeartbeatReceiveInterval apply to the system connection between the Spring relay and the broker. They do not replace the heartbeat negotiated for each client connection.

The broker relay automatically recovers the system connection, but client connections are not automatically restored when the broker is disconnected. The client needs to detect the lost connection and reconnect on its own; after reconnecting it must re-create the STOMP session and subscriptions.

### 9.1. Monitoring the broker relay state

Spring publishes BrokerAvailabilityEvent when the broker relay's system connection changes from available to unavailable or vice versa.

A service that sends messages through SimpMessagingTemplate can watch this event to pause sending when the broker is not ready. Even so, you must still handle MessageDeliveryException because the state can change right between the check and the send.

~~~java
@Component
public class BrokerAvailabilityMonitor {

    private volatile boolean brokerAvailable = false;

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        brokerAvailable = event.isBrokerAvailable();
        System.out.println("brokerAvailable=" + brokerAvailable);
    }

    public boolean isBrokerAvailable() {
        return brokerAvailable;
    }
}
~~~

This event tracks the system connection between Spring and the broker. It does not represent the state of each individual browser client.

### 9.2. TaskScheduler on the broker relay

Some STOMP clients, for example STOMP.js, send heartbeats on a fixed cycle. Other clients, such as Spring's WebSocketStompClient, only send heartbeats when there is no other message.

A message sent to a Spring internal destination can be handled within the application and not forwarded to the broker. If the broker receives no data within the heartbeat interval, it can mark the client's TCP connection as inactive even though the browser is still sending messages to Spring.

You can provide a scheduler for the broker relay:

~~~java
registry.enableStompBrokerRelay("/topic", "/queue")
    .setRelayHost("broker.example.com")
    .setRelayPort(61613)
    .setSystemHeartbeatSendInterval(10_000)
    .setSystemHeartbeatReceiveInterval(10_000)
    .setTaskScheduler(stompHeartbeatScheduler());
~~~

This scheduler lets the relay track the number of messages the client sends to the broker in each heartbeat cycle and send a heartbeat when needed. Enable it when the architecture has internal messages that are not relayed and the client only emits heartbeats when idle.

## 10. Spring detects a session ending through events

Spring publishes events following the STOMP session lifecycle:

| Event | Meaning |
|---|---|
| SessionConnectEvent | Received CONNECT from the client |
| SessionConnectedEvent | The broker has responded with CONNECTED |
| SessionSubscribeEvent | The client registers a subscription |
| SessionUnsubscribeEvent | The client cancels a subscription |
| SessionDisconnectEvent | The STOMP session ends |
| BrokerAvailabilityEvent | The broker relay's system connection changes state |

SessionDisconnectEvent can appear when the client sends DISCONNECT or when the WebSocket session closes due to a transport error, a heartbeat timeout, or another reason. Spring notes that this event can be published more than once for a session. Cleanup code must be idempotent.

Example of removing state by session ID:

~~~java
@Component
public class StompSessionCleanup {

    private final ConcurrentMap<String, Object> activeSessions =
        new ConcurrentHashMap<>();

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        activeSessions.remove(event.getSessionId());
    }
}
~~~

remove(sessionId) is safe when the event repeats. If the cleanup also calls an external service or writes to a database, use an idempotency key/session status to avoid processing the same disconnect multiple times.

Do not use SessionDisconnectEvent to receive notifications for each message. This event is for the lifecycle. If you need to track every message, use a ChannelInterceptor on the inbound/outbound channel.

## 11. Heartbeat, timeouts, and reverse proxies

A connection can be closed by a proxy or load balancer before the STOMP heartbeat timeout occurs. You need to reconcile the time intervals across multiple layers:

- Client → server heartbeat.
- Server → client heartbeat.
- The grace period of the STOMP client.
- The read timeout of the simple broker or the external broker.
- The idle timeout of the reverse proxy/load balancer.
- TCP keepalive and the timeouts of the operating environment.

For example, if the server sends a heartbeat about once every 10 seconds and the proxy closes an idle connection after 60 seconds, the proxy has enough traffic to keep the connection active. If heartbeat is disabled or the scheduler is hung, the proxy can close the socket before the application detects it.

Some principles:

1. The heartbeat interval must be smaller than the proxy's idle timeout with an appropriate margin.
2. The heartbeat receive timeout must be greater than the negotiated interval and have a grace period for jitter.
3. The scheduler must have active threads and not be occupied by blocking work.
4. Client reconnects need backoff; avoid reconnecting continuously on a very short cycle.
5. When the client reconnects, re-authenticate and re-create the necessary subscriptions/state.
6. Measure the number of open sessions, disconnects, heartbeat lost, reconnects, and broker availability to detect errors by trend.

Do not set every timeout to the same number. The timeouts of the broker, the browser, and the proxy serve different purposes.

## 12. Heartbeat is not ACK or RECEIPT

A heartbeat only indicates that data is flowing through the connection and that the peer is able to respond. It does not guarantee:

- That a business message has been processed.
- That the consumer has committed the database.
- That the broker has durably stored the message.
- That a subscriber has received or processed the event.
- That the user is active on the interface.

If you need to confirm that a SEND or SUBSCRIBE operation has been processed by the broker, use the STOMP receipt header and receive the RECEIPT frame. If you need to confirm that the business has completed, define a separate business ACK/response and handle idempotency.

A successful heartbeat does not replace retry, ACK, NACK, receipt, or transactions.

## 13. Testing heartbeat and dead-connection detection

A test suite should include these cases:

### 13.1. An idle but still active connection

1. Connect the client and server using STOMP 1.2.
2. Enable heartbeat in both directions.
3. Send no business messages for a few cycles.
4. Confirm that the client is still connected and the server still holds the subscription.

### 13.2. A silent connection loss

1. Connect the client to the broker.
2. Block or cut the traffic in a way that does not immediately send FIN/RST (for example a network blackhole).
3. Wait past the negotiated interval plus the grace period.
4. Confirm that the broker or the client detects the timeout and the session is cleaned up.

Closing the tab or calling close() usually produces a clear close handshake/transport close; that situation does not fully test the ability to detect a silently broken connection.

### 13.3. Broker restart

With the broker relay, restart the external broker and confirm:

- BrokerAvailabilityEvent changes to unavailable.
- The system connection is retried by the relay.
- The lost client connections require the client to reconnect.
- Subscriptions are re-created in the successful-connection callback.

### 13.4. Timers and slow environments

Try a background browser tab, high CPU, a slow scheduler, and the proxy idle timeout. Confirm that the grace period is large enough to avoid false disconnects but still cleans up dead sessions within an acceptable time.

## 14. Java 17+ example: calculating the negotiated interval and timeout

This standalone example illustrates the STOMP formula and the Spring simple broker's 3x grace period. It does not open a WebSocket or connect to a broker; it checks the calculation so that learners can confirm the interval before configuring a system.

**HeartbeatNegotiationDemo.java**

~~~java
public class HeartbeatNegotiationDemo {

    record Heartbeat(long canSendMs, long wantsReceiveMs) {
        Heartbeat {
            if (canSendMs < 0 || wantsReceiveMs < 0) {
                throw new IllegalArgumentException(
                    "Heartbeat values cannot be negative"
                );
            }
        }
    }

    record NegotiatedIntervals(
            long clientToServerMs,
            long serverToClientMs) {
    }

    static long negotiate(long senderCanSendMs, long receiverWantsMs) {
        if (senderCanSendMs == 0 || receiverWantsMs == 0) {
            return 0;
        }
        return Math.max(senderCanSendMs, receiverWantsMs);
    }

    static NegotiatedIntervals negotiate(
            Heartbeat client,
            Heartbeat server) {

        long clientToServer = negotiate(
            client.canSendMs(), server.wantsReceiveMs()
        );
        long serverToClient = negotiate(
            server.canSendMs(), client.wantsReceiveMs()
        );

        return new NegotiatedIntervals(
            clientToServer,
            serverToClient
        );
    }

    static long simpleBrokerReadTimeoutMs(long clientToServerMs) {
        return clientToServerMs == 0
            ? 0
            : Math.multiplyExact(clientToServerMs, 3);
    }

    static boolean isTimedOut(long elapsedMs, long timeoutMs) {
        return timeoutMs > 0 && elapsedMs > timeoutMs;
    }

    public static void main(String[] args) {
        Heartbeat client = new Heartbeat(10_000, 15_000);
        Heartbeat server = new Heartbeat(5_000, 20_000);

        NegotiatedIntervals intervals = negotiate(client, server);
        long serverReadTimeout =
            simpleBrokerReadTimeoutMs(intervals.clientToServerMs());

        System.out.println(
            "clientToServerIntervalMs=" + intervals.clientToServerMs()
        );
        System.out.println(
            "serverToClientIntervalMs=" + intervals.serverToClientMs()
        );
        System.out.println(
            "simpleBrokerClientTimeoutMs=" + serverReadTimeout
        );
        System.out.println(
            "clientTimedOutAt60000ms=" +
                isTimedOut(60_000, serverReadTimeout)
        );
        System.out.println(
            "clientTimedOutAt60001ms=" +
                isTimedOut(60_001, serverReadTimeout)
        );
    }
}
~~~

Run with Java 17:

~~~bash
javac HeartbeatNegotiationDemo.java
java HeartbeatNegotiationDemo
~~~

**Output**

~~~text
clientToServerIntervalMs=20000
serverToClientIntervalMs=15000
simpleBrokerClientTimeoutMs=60000
clientTimedOutAt60000ms=false
clientTimedOutAt60001ms=true
~~~

Explanation:

- The client can send every 10 seconds and the server wants to receive every 20 seconds, so the client → server interval is 20 seconds.
- The server can send every 5 seconds and the client wants to receive every 15 seconds, so the server → client interval is 15 seconds.
- The Spring simple broker uses three times the read interval as the client read timeout, so the threshold in the example is 60 seconds.
- At exactly 60,000 ms, the condition elapsed > timeout is not yet true; once it exceeds 60,000 ms, the client is considered timed out.

The factor of 3 in the example simulates the Spring simple broker implementation. The STOMP specification only requires an error margin, and other clients and brokers can use a different grace period.

## 15. Common mistakes

1. **Enabling heartbeat only on the client side:** the server and client must negotiate both directions; one direction can be disabled if the other side's value is 0.
2. **Forgetting the TaskScheduler with the simple broker:** configuring a heartbeat other than [0,0] without a scheduler causes the broker to be unable to run the heartbeat task.
3. **Confusing the server heartbeat values:** the first element of setHeartbeatValue is what the server sends; the second element is what the server wants the client to send.
4. **Treating the interval as an exact timeout:** a grace period is needed; the Spring simple broker uses a factor of 3 for the read timeout.
5. **Thinking only a heartbeat refreshes liveness:** other STOMP data also counts as activity.
6. **Confusing WebSocket Ping/Pong with STOMP heartbeat:** they are at two different protocol layers.
7. **Disabling heartbeat with 0,0 but still expecting idle detection:** when a direction is disabled, there is no STOMP heartbeat timeout for that direction.
8. **A proxy timeout shorter than the heartbeat:** the proxy can close the socket before the heartbeat arrives.
9. **Using a heartbeat that is too short:** it creates a lot of traffic and scheduler tasks, increasing the load on the broker and the client.
10. **Not handling background browser tabs:** timers can be throttled; consider STOMP.js's Worker strategy.
11. **Thinking the broker relay automatically reconnects every client:** the relay reconnects the system connection on its own; client sessions need to reconnect on the client side.
12. **Not monitoring BrokerAvailabilityEvent:** the application may send to the broker while the system connection is unavailable.
13. **Non-idempotent SessionDisconnectEvent handling:** the event can repeat for the same session; cleanup must be safe when called multiple times.
14. **Using heartbeat as a business ACK:** a heartbeat does not confirm that a message has been processed or durably stored.
15. **Not testing a network blackhole:** closing the socket normally does not fully simulate a silently broken connection.

## 16. Deployment checklist

Before putting STOMP heartbeat into production, check:

1. Do the client and server use STOMP 1.1+ and exchange heart-beat in CONNECT/CONNECTED?
2. Are the two heartbeat directions negotiated correctly according to the max formula?
3. Does the Spring simple broker have a TaskScheduler and an appropriate heartbeat value?
4. Does the external broker have its own heartbeat timeout/grace period that needs configuring?
5. Are the broker relay system heartbeat and the client heartbeat clearly distinguished?
6. Does the client detect heartbeat lost and reconnect with backoff?
7. Are subscriptions restored after a reconnect?
8. Is the SessionDisconnectEvent cleanup idempotent?
9. Is BrokerAvailabilityEvent monitored when using an external broker relay?
10. Is the proxy/load balancer idle timeout larger than the heartbeat plus the grace period?
11. Have the scheduler, CPU, browser background timers, and network jitter been tested?
12. Do the metrics include active sessions, disconnects, heartbeat lost, reconnects, and broker availability?
13. Have separate ACK/RECEIPT business needs been implemented?

## 17. Conclusion

STOMP heartbeat lets the client and server know whether the connection is still exchanging data or has stopped responding. The two sides declare their ability to send and their need to receive in CONNECT/CONNECTED, and then negotiate an independent interval for each direction using the max formula.

In the Spring simple broker, the TaskScheduler runs the heartbeat task, sends heartbeats when outbound is idle, and removes a session when the client sends no data beyond the read timeout. With an external broker relay, the system connection and each client connection have their own heartbeat lifecycle; the relay recovers the system connection on its own, while the client must reconnect on its own.

A good configuration needs to align the interval, grace period, proxy timeout, scheduler, and reconnect. Heartbeat monitors liveness; ACK, RECEIPT, and business confirmation still need their own mechanisms.

## 18. References

- [STOMP Protocol Specification 1.2 — Heart-beating](https://stomp.github.io/stomp-specification-1.2.html#Heart-beating)
- [Spring Framework 6.2 — Simple Broker](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/handle-simple-broker.html)
- [SimpleBrokerRegistration — Spring Framework 6.2.18 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/simp/config/SimpleBrokerRegistration.html)
- [Spring Framework 6.2 — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/handle-broker-relay-configure.html)
- [StompBrokerRelayRegistration — Spring Framework 6.2.18 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)
- [Spring Framework 6.2 — STOMP Application Context Events](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/application-context-events.html)
- [WebSocketStompClient — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html)
- [STOMP.js Client API — Heartbeats and Reconnection](https://stomp-js.github.io/api-docs/latest/classes/Client.html)