# Limits of Long-Lived Connections When Client or Server Disconnects

WebSocket creates a long-lived bidirectional connection between the client and the server. This connection enables continuous data exchange without opening a new HTTP request for each message, but the connection itself does not store message history and does not automatically restore application state after the network is cut.

When the client, server, proxy, or broker loses connectivity, the application must solve three separate tasks:

1. **Detection:** recognize that the connection has died or is no longer responding.
2. **Reconnection:** establish a new WebSocket/STOMP session and re-register whatever is needed.
3. **Data recovery:** determine which messages arrived, which messages were missed, and how to continue without duplicate processing.

Spring Framework provides callbacks, events, heartbeats, and transport limits to support these tasks. Reconnection and business data recovery still need to be designed according to the application's requirements.

## 1. How Does a Long-Lived WebSocket Connection Work?

WebSocket starts with an HTTP opening handshake. When the handshake succeeds, both sides switch to exchanging WebSocket frames over the open TCP connection.

~~~text
Client                         Server
  |                               |
  |------ HTTP Upgrade ---------->|
  |<----- 101 Switching ----------|
  |                               |
  |<==== WebSocket frames ========>|
  |                               |
  |------ Close frame ------------>|
  |<----- Close frame -------------|
  |                               |
  |------ TCP connection closed --|
~~~

The connection is stateful at the transport layer. Both sides can send text frames, binary frames, ping, pong, and close frames. While the connection stays active, TCP provides an ordered byte stream and network-layer retransmission.

However, WebSocket does not provide on its own:

- A message store while the client is offline.
- Message replay after reconnect.
- A business-level acknowledgement that the client finished processing.
- Restoration of in-memory subscriptions or state after a server restart.
- A guarantee that the client is always online or that the server always keeps the socket open.

If you need those behaviors, the application must use a broker with appropriate storage capabilities or build event storage, cursors, acknowledgements, and resume mechanisms at the business layer.

## 2. Types of Disconnection

### 2.1. Intentional Disconnection

One side sends a WebSocket Close frame to start the closing handshake. Both sides exchange Close frames and then close the TCP connection.

Common scenarios:

- The user closes the tab or leaves the page.
- The client calls close() on logout.
- The server closes sessions during deployment or maintenance.
- The application proactively rejects a session that is no longer valid.

A Close frame can carry a status code and reason. Code 1000 indicates normal closure; 1001 is commonly used when an endpoint is going away, such as a server shutdown.

### 2.2. Sudden Network Loss

The client may lose Wi-Fi, switch networks, sleep, or lose cellular signal. The server may be killed, crash its process, restart its host, or have network routes changed.

In this case, the two sides may not be able to exchange Close frames. The TCP connection can remain in a half-open state for a while because one side does not yet know the link is lost.

Clients usually observe an abnormal closure via close code 1006. This is a code reserved for an abnormal state observed by the local endpoint; it must not be sent directly inside a Close frame on the wire.

### 2.3. Proxy or Load Balancer Closing an Idle Connection

A connection with no data for a long time may be closed by a reverse proxy, firewall, NAT, or load balancer due to an idle timeout.

The application may see the socket close even though both the client and server are still operating normally. If heartbeats are not configured or do not traverse the full network path, intermediary devices may treat the connection as idle.

### 2.4. Server Restart or Deployment

When a Spring node restarts, every WebSocket session inside that process is lost. Spring does not automatically migrate sockets to another node.

The client must create a new connection. The new server must re-authenticate the client, create a new session, and restore the required subscriptions/state according to the application contract.

### 2.5. Client Still Connected but No Longer Reading Data

A slow client, a frozen tab, or a low-bandwidth device may keep the socket open while failing to consume messages fast enough. The server keeps writing data into the buffer until the limit is reached.

This is the slow consumer/backpressure problem. It can increase memory usage, increase latency, and affect other clients if the buffer is not bounded.

## 3. What Is Guaranteed While the Connection Is Active?

TCP/WebSocket preserves the order of bytes/frames on an active connection. If the connection is closed, there is no guarantee that the application knows exactly up to which last message the other side processed.

Example:

1. The server sends event E42.
2. The TCP stack accepts the data for sending.
3. The client may have received the frame but not processed it yet.
4. The network drops before the client sends an application-layer acknowledgement.
5. The server cannot know for sure whether the client completed the business operation or not.

A send call that succeeds or throws no exception does not prove that the client read, saved, or processed the message. It only reflects the send result at the transport/API layer at that moment.

If processing confirmation is needed, define an acknowledgement at the application layer. For example, the client sends an ACK containing the event ID or sequence number after saving the data successfully. The server marks the event as processed only when it receives the appropriate ACK.

## 4. Detecting Dead Connections with Ping/Pong

RFC 6455 defines Ping and Pong control frames:

- An endpoint may send a Ping while the connection is open.
- Upon receiving a Ping, an endpoint must respond with a Pong, unless the connection has already started closing.
- Ping can be used as a keepalive or to check whether the peer endpoint still responds.
- The Pong response must carry the same application data as the corresponding Ping.

Heartbeats help detect connections that are no longer responsive. If a Ping is sent without receiving a Pong within the configured deadline, the endpoint can treat the connection as lost and close it.

One note for browsers: the WebSocket JavaScript API does not provide methods for JavaScript applications to send or receive Ping/Pong control frames themselves. The browser handles control frames at the protocol layer. For browser clients, you can use STOMP heartbeats or application-level heartbeats if control from JavaScript is needed.

Heartbeats do not guarantee instant detection. Detection timing depends on the heartbeat interval, timeout, scheduler, network delay, and whether processing threads are blocked.

## 5. Heartbeats at the STOMP and SockJS Layers

### 5.1. STOMP Heartbeat

When using STOMP over WebSocket, the client and server can negotiate heartbeats via the heart-beat header of STOMP CONNECT/CONNECTED.

The two values represent the minimum intervals at which each side expects to send data/heartbeats. A value of 0 means that side does not send heartbeats in the corresponding direction. A heartbeat is sent only when no other message is sent within the required interval.

With Spring WebSocketStompClient, you can configure a TaskScheduler and the default heartbeat:

~~~java
WebSocketStompClient stompClient =
        new WebSocketStompClient(new StandardWebSocketClient());

stompClient.setTaskScheduler(heartbeatScheduler);
stompClient.setDefaultHeartbeat(
        new long[] {10_000, 10_000}
);
~~~

TaskScheduler is used to schedule heartbeats and track STOMP receipts. When no scheduler is configured, WebSocketStompClient's default heartbeat may be disabled; setting a scheduler activates the appropriate default values if not otherwise configured.

On the server, the simple broker also needs a TaskScheduler to send and check heartbeats:

~~~java
registry.enableSimpleBroker("/topic", "/queue")
        .setHeartbeatValue(new long[] {10_000, 10_000})
        .setTaskScheduler(messageBrokerTaskScheduler);
~~~

The 10-second intervals in the example are illustrative values. Choose intervals and timeouts based on the proxy idle timeout, network latency, system load, and number of connections. Do not set heartbeats too frequently when there are tens of thousands of clients if the scheduler is not sized appropriately.

### 5.2. SockJS Heartbeat

When using the SockJS fallback, Spring by default sends a heartbeat after about 25 seconds if the connection has no other messages. Heartbeats help prevent proxies from treating HTTP streaming/long polling connections as hung.

If the STOMP client and server have already negotiated heartbeats, the SockJS heartbeat is disabled to avoid sending two overlapping heartbeat mechanisms.

With HTTP streaming or long polling, the Servlet API does not provide direct notifications for every case where a client has disappeared. The server usually detects the disconnect only when the next write fails; heartbeats help generate periodic writes to detect it sooner.

## 6. Callbacks and Events for Detecting Disconnects in Spring

### 6.1. Raw WebSocketHandler

When implementing WebSocketHandler or TextWebSocketHandler, important callbacks include:

- afterConnectionEstablished: the handshake succeeded and the session is ready.
- handleTransportError: the transport reported an error while reading/writing or handling a message.
- afterConnectionClosed: the connection closed or a transport error occurred.

Example:

~~~java
@Component
public class PresenceWebSocketHandler extends TextWebSocketHandler {

    private final PresenceService presenceService;

    public PresenceWebSocketHandler(PresenceService presenceService) {
        this.presenceService = presenceService;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        presenceService.connected(
                session.getId(),
                session.getPrincipal()
        );
    }

    @Override
    public void handleTransportError(
            WebSocketSession session,
            Throwable exception) {

        presenceService.markTransportError(session.getId(), exception);
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session,
            CloseStatus status) {

        presenceService.disconnected(
                session.getId(),
                status.getCode()
        );
    }
}
~~~

The example illustrates lifecycle hooks. PresenceService needs to handle state updates safely when both the error callback and close callback occur. Do not assume a single callback will always fully describe the cause of connection loss.

After afterConnectionClosed is called, continuing to send messages over that session is not recommended and will usually fail.

### 6.2. STOMP SessionDisconnectEvent

When using STOMP, Spring publishes events such as:

- SessionConnectEvent: STOMP CONNECT was received.
- SessionConnectedEvent: the broker replied with CONNECTED, and the STOMP session is established.
- SessionSubscribeEvent and SessionUnsubscribeEvent: the client registered or canceled a subscription.
- SessionDisconnectEvent: the STOMP session ended.

SessionDisconnectEvent may be published more than once for the same session. The listener handling this event must be idempotent.

~~~java
@Component
public class StompSessionLifecycleListener {

    private final PresenceService presenceService;

    public StompSessionLifecycleListener(
            PresenceService presenceService) {
        this.presenceService = presenceService;
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        presenceService.removeIfPresent(event.getSessionId());
    }
}
~~~

Use the session ID to clean up the state of the corresponding connection. If the business logic manages online/offline status per user, account for the fact that the same user can open multiple tabs or devices; closing one session does not mean the user is completely offline.

## 7. The Client Must Reconnect on Its Own

Spring STOMP broker relay can automatically reconnect the system connection between the Spring application and the broker when the broker recovers. Disconnected WebSocket clients are not automatically reconnected by that mechanism. Clients need to perform reconnects themselves.

A common strategy is exponential backoff with jitter:

1. Try reconnecting after a short interval.
2. If it keeps failing, gradually increase the wait time.
3. Set a maximum cap so it does not wait too long.
4. Add random jitter so many clients do not reconnect simultaneously.
5. Reset the retry counter after the connection has been stable for a period of time.

Example JavaScript client logic:

~~~javascript
let retryAttempt = 0;
let manuallyStopped = false;

function scheduleReconnect() {
    if (manuallyStopped) {
        return;
    }

    const ceiling = Math.min(30_000, 500 * (2 ** retryAttempt));
    retryAttempt = Math.min(retryAttempt + 1, 10);

    const delay = Math.random() * ceiling;
    window.setTimeout(connect, delay);
}

function connect() {
    const socket = new WebSocket("wss://example.com/ws");

    socket.addEventListener("open", () => {
        restoreSubscriptionsAndResumeState(socket);

        window.setTimeout(() => {
            if (socket.readyState === WebSocket.OPEN) {
                retryAttempt = 0;
            }
        }, 30_000);
    });

    socket.addEventListener("close", () => {
        scheduleReconnect();
    });

    socket.addEventListener("error", () => {
        socket.close();
    });
}
~~~

This is an illustrative snippet for a browser client; the application needs to add timer management, cancel reconnects when the user logs out, prevent creating multiple sockets concurrently, and handle authentication errors. In a STOMP application, after a WebSocket connection succeeds, it must also send STOMP CONNECT, wait for CONNECTED, and then re-register the required destinations.

Do not reset the retry counter right when the socket just opens. If the connection keeps opening and closing after a few seconds, resetting immediately will cause the client to repeat rapid retries indefinitely.

## 8. Reconnect Does Not Automatically Restore Subscriptions and State

A new WebSocket session has a new session ID. Subscriptions, pending requests, session attributes, and data kept only in the old connection's memory may no longer exist.

After reconnecting, the client should perform steps in order:

1. Open the WebSocket connection.
2. Re-authenticate and establish the STOMP session if using STOMP.
3. Re-register destinations.
4. Send the last cursor/sequence number that the client processed successfully.
5. Receive the missing events or load a new snapshot.
6. Send acknowledgements for processed events per the contract.

Do not use the WebSocket session ID as a long-term user identifier. Use an authenticated user ID, device ID, or an appropriate business client identity; a session ID represents only a single connection.

If the server restarts, any state living only in that node's memory can be lost. State that must survive restarts must be stored in an appropriate database, distributed cache, or broker.

## 9. Messages Lost or Processed Twice When a Connection Drops

Suppose the server sends events E100, E101, E102 during an unstable network. The client receives E100 and E101, but the connection drops before E102 arrives.

If the server has no event log or replay mechanism, the client has no way to request E102 again. Conversely, if the client receives E101 but the ACK is lost, the server may send E101 again on reconnect.

These are two common situations:

- **Message gap:** the client missed one or more messages while offline.
- **Duplicate delivery:** the client receives a message already processed because the previous acknowledgement did not reach the server.

A resume protocol should have:

- A unique eventId to deduplicate.
- An increasing sequence number per stream or partition.
- The last cursor the client confirmed it processed.
- A store for events to replay.
- An acknowledgement after the client saves/processes successfully.
- A retention policy defining how long replay is possible.

Example payload:

~~~json
{
  "eventId": "evt-1002",
  "sequence": 1002,
  "type": "OrderUpdated",
  "data": {
    "orderId": "ORD-42",
    "status": "PAID"
  }
}
~~~

On reconnect, the client sends lastProcessedSequence=1001. The server can replay from sequence 1002 if the event is still within retention. The client stores processed eventIds or sequences to skip duplicates.

WebSocket only transports messages. Storing events, replay, and deduplication belong to the application or broker layer.

## 10. STOMP Receipt, Acknowledgement, and Business Processing

STOMP has receipts so the client can ask the server to send a RECEIPT frame after a send/subscribe frame is processed on the server side. Receipts help tell whether the server processed the frame according to STOMP semantics.

A receipt does not by itself prove that a database transaction or business side effects on the client/server completed. If business confirmation is needed, define a separate application ACK containing the event ID, result, and sequence.

STOMP subscriptions have acknowledgement modes such as auto, client, and client-individual. Choose the mode according to broker semantics and how the client processes messages. If using an external broker, check how the broker stores subscriptions and handles unacknowledged messages when a connection closes.

Spring simple broker stores subscriptions in memory and delivers messages to connected clients. It is not a durable message store for offline clients. If you need durable subscriptions or replay while offline, use an external broker that supports those features and configure it according to the broker's documentation.

## 11. Broker and WebSocket Connections Are Two Different Connections

In the Spring STOMP broker relay architecture, there are at least two groups of connections:

- WebSocket connections from browsers/clients to the Spring application.
- TCP/STOMP connections from the Spring broker relay to the message broker.

The broker relay can reconnect the system connection when the broker restarts. Spring publishes BrokerAvailabilityEvent when the system connection status changes. Components sending via SimpMessagingTemplate should monitor this status and be ready to handle MessageDeliveryException if the broker is not ready yet.

The fact that the system connection recovered does not automatically make dropped WebSocket clients reconnect. Clients need to open new sessions and re-register subscriptions.

If the broker supports durable subscriptions, configure durable subscriptions per the broker/STOMP client contract. Spring simple broker does not provide persistence for offline subscriptions or messages.

## 12. Limits of Proxies, Load Balancers, and Servers

A long-lived connection is affected by every component along the transmission path:

- Reverse proxies and load balancers have idle timeouts.
- Firewalls and NATs may clear mappings when there is no traffic.
- The Servlet container or WebSocket engine has idle timeouts and buffer limits.
- The operating system has limits on file descriptors, sockets, and memory.
- The Spring application has limits on connections, schedulers, thread pools, and send buffers.
- The broker has limits on connections, subscriptions, and message storage capacity.

Heartbeats should be sent more frequently than the shortest idle timeout along the entire network path, leaving a safety margin for scheduler delay and network jitter.

If a proxy closes a connection after 60 seconds of idle time, a heartbeat every 90 seconds will not protect the socket. Conversely, heartbeats that are too frequent increase traffic and scheduler work when the client count is large.

Idle timeout configurations must be aligned across the client, server, proxy, and broker. Do not assume that increasing a timeout on the Spring server changes timeouts enforced by a load balancer or firewall.

## 13. Slow Consumers, Send Buffers, and Message Size Limits

A low-bandwidth client may consume data more slowly than the rate at which the server emits it. Spring must buffer messages waiting to be sent. If unbounded, the buffer can grow and cause memory pressure.

With STOMP over WebSocket, you can configure transport limits:

~~~java
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {

    registration
            .setMessageSizeLimit(64 * 1024)
            .setSendTimeLimit(15_000)
            .setSendBufferSizeLimit(512 * 1024);
}
~~~

Meaning:

- messageSizeLimit limits the size of sub-protocol messages such as a STOMP frame after being assembled from WebSocket messages.
- sendTimeLimit limits the time allowed to send to a session.
- sendBufferSizeLimit limits the amount of data waiting to be sent to a session.

The numbers are initial examples and need to be adjusted according to actual payloads, client counts, and bandwidth. When limits are exceeded, Spring can clear the send state and close the session to protect resources.

With a raw WebSocketHandler, you can use ConcurrentWebSocketSessionDecorator to serialize sending and limit the buffer:

~~~java
WebSocketSession safeSession =
        new ConcurrentWebSocketSessionDecorator(
                session,
                10_000,
                512 * 1024
        );

safeSession.sendMessage(new TextMessage("update"));
~~~

You should create the wrapper once per session and reuse it. A standard WebSocket session does not allow multiple threads to send concurrently; the decorator ensures one thread sends at a time and buffers competing sends.

With a Jakarta WebSocket server, you can configure text/binary buffer limits on the server container:

~~~java
@Bean
public ServletServerContainerFactoryBean webSocketContainer() {
    ServletServerContainerFactoryBean container =
            new ServletServerContainerFactoryBean();

    container.setMaxTextMessageBufferSize(64 * 1024);
    container.setMaxBinaryMessageBufferSize(64 * 1024);

    return container;
}
~~~

Server container limits and STOMP frame limits are two different layers. Check both if the application uses STOMP.

## 14. Scaling Many Clients and Multiple Server Nodes

A WebSocket connection is held by a specific process/node throughout the socket's lifetime. When a client reconnects, the load balancer may route it to another node.

Sticky sessions can help an existing connection continue going to the same node, but do not replicate one node's state to another node. If the old node dies, the client still has to reconnect and the application must restore state from a shared source.

With multiple Spring nodes, consider:

- Use an external broker to distribute messages across nodes.
- Store presence, subscription metadata, or necessary session mappings in a shared store if the business requires it.
- Use a user registry and an appropriate broadcast mechanism when routing to users connected on other nodes is needed.
- Avoid using a static Map in a single node as the sole source of truth for online status.
- Design graceful shutdown to stop accepting new connections, notify clients to reconnect, and close sessions in a controlled manner.

If servers deploy all at once, thousands of clients may reconnect simultaneously. Jitter, backoff, and handshake rate limiting help prevent a reconnect storm.

## 15. Authentication and Session Expiry

The initial WebSocket handshake usually goes over HTTP, so authentication can rely on cookies/sessions or HTTP authentication mechanisms. After upgrading, the connection lives longer than an ordinary HTTP request.

If an access token expires while the socket is still open, do not assume the connection automatically closes or access rights automatically update. The application must decide how to handle it:

- Close the connection when credentials expire.
- Require the client to refresh credentials and then reconnect.
- Send an application-level notification requiring re-authentication.
- Check permissions on sensitive messages if policy requires it.

On reconnect, perform the handshake and re-authenticate according to the active security mechanism. Do not trust user IDs or roles sent by the client itself in STOMP headers. Check Origin, subscribe/send permissions, and input data according to the endpoint's security policy.

Also avoid putting access tokens into the query string if URLs may be logged in access logs, proxy logs, or browser history.

## 16. Example Configuring STOMP Heartbeat and Transport in Spring

The configuration example below illustrates the simple broker with heartbeats and send limits:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    private final TaskScheduler heartbeatScheduler;

    public WebSocketConfiguration(TaskScheduler heartbeatScheduler) {
        this.heartbeatScheduler = heartbeatScheduler;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[] {10_000, 10_000})
                .setTaskScheduler(heartbeatScheduler);

        registry.setApplicationDestinationPrefixes("/app");
    }

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {

        registration
                .setMessageSizeLimit(64 * 1024)
                .setSendTimeLimit(15_000)
                .setSendBufferSizeLimit(512 * 1024);
    }
}
~~~

You can declare a separate scheduler:

~~~java
@Bean
public ThreadPoolTaskScheduler heartbeatScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("ws-heartbeat-");
    return scheduler;
}
~~~

This configuration applies to Spring's built-in STOMP message broker. If using a broker relay, configure heartbeats and reconnect at the broker relay layer per the broker's requirements; if using a raw WebSocketHandler, configure server/container limits and manage send concurrency accordingly.

## 17. Monitoring Connections and Disconnect Causes

Do not just count connect/disconnect events. You also need to observe connection quality and send load.

Useful metrics:

- Number of open WebSocket sessions per node.
- Number of sessions created/closed over a period of time.
- Number of disconnects by close status and transport error.
- Heartbeat timeouts and disconnect detection time.
- Client reconnect counts, reconnect times, and reconnect success rate.
- Counts of STOMP CONNECT, CONNECTED, DISCONNECT, and SUBSCRIBE frames.
- Send time limit exceeded and send buffer limit exceeded counts.
- Buffer size, message size, and outbound latency.
- Number of slow clients, dropped messages, or replayed messages.
- Broker relay status and system connection reconnect counts.

Spring provides SessionConnectEvent, SessionConnectedEvent, SessionDisconnectEvent, and BrokerAvailabilityEvent to monitor the lifecycle. SessionDisconnectEvent may occur multiple times for a single session, so cleanup and business metrics must guard against duplicate processing.

Do not log full payloads or tokens to diagnose disconnects. Prefer session IDs, authenticated user identities, close codes, error types, and appropriate correlation IDs.

## 18. Testing Disconnect Scenarios

A test that only opens a WebSocket and sends one message is not enough to test the reliability of a long-lived connection.

Scenarios should include:

1. Client closes normally with a Close frame.
2. Client loses network without sending a Close frame.
3. Server restarts while many sessions are active.
4. Proxy idle timeout shorter than heartbeat to confirm misconfiguration failure.
5. Heartbeat timeout when peer does not respond.
6. Client reconnects with exponential backoff and jitter.
7. Client re-registers STOMP subscriptions after reconnecting.
8. Client sends cursor and server replays missing events.
9. ACK is lost causing an event to be re-sent; client deduplicates by event ID.
10. Slow consumer causes send buffer to hit the limit.
11. Message exceeds container or STOMP transport size limit.
12. Broker relay loses connection and then recovers the system connection.
13. Client reconnects to another Spring node.
14. Token expires while the connection is open.
15. Many clients reconnect simultaneously after a deployment.

Reconnect tests should use latches, polling with timeouts, or observable conditions instead of fixed sleeps. When testing message loss, clearly determine where messages are stored and which acknowledgement is considered complete.

## 19. Common Mistakes

### 19.1. Thinking WebSocket Reconnects Automatically

The WebSocket protocol does not automatically establish a new connection after the old connection closes. The client must call connect again and handle errors.

### 19.2. Thinking Heartbeats Guarantee No Message Loss

Heartbeats only check connection liveness. They do not store messages, confirm business processing, or replay data.

### 19.3. Only Handling the Close Event on the Client

The network can drop suddenly so the server never receives a Close frame. The server needs heartbeats, transport error handling, and timeout mechanisms to clean up stale sessions.

### 19.4. Using Session ID as a Long-Term Identifier

A session ID is tied to one connection. After reconnecting, the ID can change. Use an authenticated business identity to restore state.

### 19.5. Not Re-registering Subscriptions

A new STOMP session does not automatically keep the old session's subscriptions. The client must SUBSCRIBE again after CONNECTED.

### 19.6. Believing a Successful Send Means the Client Processed It

A transport write is not a business acknowledgement. Use an application-layer ACK when processing confirmation is needed.

### 19.7. Not Limiting Buffers for Slow Clients

Messages sent faster than the consumption rate cause the buffer to grow. Configure send time limits, send buffer sizes, and appropriate drop/coalesce policies.

### 19.8. Setting Heartbeat Longer Than Proxy Idle Timeout

The proxy can close the connection before the next heartbeat is sent. Choose a heartbeat lower than the shortest timeout along the transmission path.

### 19.9. Assuming Broker Relay Reconnect Is Client Reconnect

The broker relay only restores Spring's connection to the broker. WebSocket clients still need to open new sessions themselves.

### 19.10. Non-Idempotent Disconnect Cleanup

Spring may publish SessionDisconnectEvent multiple times. If cleanup runs twice, it can distort presence counts or record duplicate logouts. Use remove-if-present operations or versioned state.

## 20. Long-Lived Connection Design Checklist

- Does the client detect socket close, errors, and heartbeat timeouts?
- Is the heartbeat configured at the right WebSocket, STOMP, or SockJS layer?
- Is the interval lower than the proxy/load balancer idle timeout?
- Does reconnection have exponential backoff, jitter, and retry limits?
- Does the client prevent multiple reconnect loops from running concurrently?
- After reconnecting, does it re-authenticate and re-register subscriptions?
- Is there a cursor/sequence to detect message gaps?
- Are there event IDs and idempotency to handle duplicates?
- Is there an application ACK if business confirmation is needed?
- Is important state stored in an appropriate shared store or broker?
- Are there send buffer and send time limits for slow clients?
- Are message size limits configured at both the server container and sub-protocol?
- Does the server handle duplicate disconnect events safely?
- Is broker relay availability monitored?
- Can multiple nodes accept reconnecting clients without losing state?
- Are server restarts, network partitions, proxy timeouts, and reconnect storms tested?

## 21. References

- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)
- [Spring Framework 6.1 — WebSocket API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/socket/WebSocketSession.html)
- [Spring Framework 6.1 — WebSocketHandler](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/socket/WebSocketHandler.html)
- [Spring Framework 6.1 — ConcurrentWebSocketSessionDecorator](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/socket/handler/ConcurrentWebSocketSessionDecorator.html)
- [Spring Framework 6.1 — WebSocketStompClient](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html)
- [Spring Framework 6.1 — SessionDisconnectEvent](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/socket/messaging/SessionDisconnectEvent.html)
- [Spring Framework Reference — STOMP Client and Heartbeats](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework Reference — STOMP Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework Reference — WebSocket Performance and Send Limits](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html)
- [Spring Framework Reference — SockJS Heartbeats and Client Disconnects](https://docs.spring.io/spring-framework/reference/web/websocket/fallback.html)

A WebSocket connection enables continuous data exchange while the session lives. When the client or server disconnects, the application must detect the failure, create a new session, and recover data per its own contract. Heartbeats help detect unresponsive peers; reconnection reopens the transport; event logs, cursors, acknowledgements, and idempotency solve continuing the data stream safely.