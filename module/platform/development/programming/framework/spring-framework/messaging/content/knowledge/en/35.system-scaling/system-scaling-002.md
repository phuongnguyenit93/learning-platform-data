# WebSocket Load Balancing, Proxy Timeouts, and Session Affinity Requirements

## 1. Challenges of Running WebSocket in Production

WebSocket creates a long-lived, bidirectional channel between client and server. The connection begins with an HTTP handshake; if the server accepts the Upgrade request, the connection switches to the WebSocket protocol and subsequent frames travel over the same TCP connection.

In production environments, endpoints usually sit behind a reverse proxy or load balancer. These components may:

- Select the application instance that receives the handshake.
- Terminate TLS and forward the connection to Spring.
- Enforce an inactivity duration limit (idle timeout).
- Close connections when a backend becomes unhealthy, during deployment, or when resource limits are exceeded.
- Distribute HTTP requests for SockJS fallbacks.
- Apply cookies or routing rules to keep a client pinned to the same instance.

Three issues must be addressed separately:

1. **Load balancing:** distributing new connections across instances to utilize resources.
2. **Proxy timeout:** keeping connections alive long enough while still detecting truly dead connections.
3. **Session affinity (sticky session):** ensuring requests belonging to the same logical session are routed to the right instance when the application needs local state.

Do not treat these three issues as a single configuration setting. A system may load-balance WebSockets well yet still drop connections after 60 seconds due to a proxy timeout; or it may have sticky sessions yet still fail to send notifications to a user connected to a different instance.

## 2. How Is a WebSocket Connection Bound to a Backend?

The load balancer selects a backend when it receives the HTTP Upgrade request. Once the handshake succeeds, the proxy turns the connection into a bidirectional tunnel. Subsequent WebSocket frames travel over that TCP tunnel and continue going to the same backend that received the handshake.

```text
Browser
   |
   | HTTP GET + Upgrade: websocket
   v
Reverse proxy / Load balancer
   |
   | selects app-2
   | returns 101 Switching Protocols
   v
Spring app-2
   |
   | WebSocket frames over the same TCP connection
   |-------------------------------------------->
   |<--------------------------------------------
   |
   +-- connection's session, principal, subscriptions
```

This leads to an important point: **the load balancer does not re-select a backend for every WebSocket frame**. An open WebSocket is already bound to a backend via its TCP connection. Cookie-based stickiness is not needed solely to keep frames of a native WebSocket on the same instance.

However, the backend still holds the state of the session, principal, subscriptions, and internal channels. If the connection closes and the client reconnects, that is a new connection. The load balancer may pick a different instance. Session affinity can help a reconnect return to the old instance, but it cannot recover a lost TCP connection or state that was wiped when an instance died.

Distinguish between:

- **Connection affinity:** frames of an active native WebSocket travel over the same TCP tunnel.
- **HTTP session affinity:** subsequent HTTP requests carrying the same cookie or routing key are sent to the same application instance.
- **Application session continuity:** login data, subscriptions, or business state can be recovered after the client reconnects, even if the instance changes.

These three concepts are related, but they do not replace one another.

## 3. When Are Sticky Sessions Needed?

### Native WebSocket

With native WebSocket, one HTTP Upgrade request creates a long-lived bidirectional connection. Once the tunnel is established, the proxy keeps the connection with the chosen backend. Sticky cookies are unnecessary for frames on that connection.

Session affinity can still be useful for other HTTP requests from the same user—such as REST APIs sharing the same `JSESSIONID`—or when the application keeps authentication state and session data only in one node's memory.

### SockJS HTTP Streaming and Long Polling

SockJS can use WebSocket, HTTP streaming, or HTTP long polling depending on browser and network capabilities. With HTTP fallback transports, a single logical SockJS session can consist of multiple HTTP requests:

- One long-lived request for the server to push messages down to the client.
- Separate HTTP POST requests for the client to send messages up to the server.
- Long polling may complete the current request and open the next request.

Those requests must be processed as the same SockJS session. If the load balancer distributes them to different instances while session state lives only in one node's memory, the instance receiving a subsequent request may not find the session or may lack the required message cache.

Therefore, with SockJS HTTP fallbacks, you need a consistent routing strategy based on cookies, client address, or `server-id` in the URL. Spring SockJS uses transport URLs of the form:

```text
/myEndpoint/{server-id}/{session-id}/{transport}
```

Here, `session-id` correlates requests belonging to the same logical session; `server-id` is useful for routing requests in a cluster. The load balancer can use a stable key to send these requests to the same node.

Spring SockJS has the `sessionCookieNeeded` property, enabled by default because many Java applications rely on cookies such as `JSESSIONID`. This property helps the SockJS client choose an appropriate transport when cookies matter. **It does not configure sticky sessions on the load balancer itself.** The infrastructure must still perform consistent routing.

### Reconnecting After Connection Drop

When a WebSocket drops, the client opens a new connection. If the selected backend differs from the old node:

- The principal may be re-established from a cookie or token.
- The HTTP session may be loaded from a shared session store.
- STOMP subscriptions must be re-registered.
- Data held only in the old node's memory may no longer exist.
- Messages sent during the disconnection window may be missed if the application lacks a storage and replay mechanism.

Sticky sessions can route reconnects back to the old node while that node is healthy, but they cannot guarantee continuity when the node dies or is removed from the pool. If resilience is required, store critical state outside local memory and design an explicit reconnect/resubscribe protocol.

## 4. Choosing a Load-Balancing Strategy for Long-Lived Connections

A WebSocket connection can stay open for minutes or hours. Therefore, the number of open connections heavily affects load distribution.

Common strategies:

| Strategy | How It Works | When Appropriate |
|---|---|---|
| Round robin | Distributes new connections sequentially across backends | Nodes have similar capacity and relatively uniform load |
| Least connections | Prefers the backend with fewer open connections | Long-lived connections where connection count is a useful load indicator |
| Cookie affinity | Routes requests with the same cookie to the same node | SockJS fallback or local HTTP session state |
| IP hash | Hashes the source IP address to pick a backend | Environments without cookie affinity, after evaluating NAT/proxies |
| Consistent hash by path/key | Uses `server-id` or session key to pick a stable node | SockJS HTTP transports and systems with explicit routing keys |

`least_conn` is usually a reasonable starting choice for native WebSocket, though connection count does not capture the full cost. A node with fewer connections where each sends thousands of messages per second can still be busier than a node with many idle connections.

Also measure:

- Active WebSockets per node.
- STOMP sessions and subscriptions.
- Inbound/outbound messages per second.
- CPU, heap, direct memory, and file descriptor counts.
- Inbound/outbound channel queues.
- Send buffers and slow client counts.
- Connections to the external broker.

`ip_hash` can cause load imbalance when many users exit to the Internet through the same NAT or proxy. When you have a choice, cookie-based affinity or an explicit routing key is usually easier to control. If using IP hash, understand which proxy is seen as the source address and trust client address headers only from trusted proxies.

Scaling out also affects only new connections. Existing open WebSockets remain on the old nodes until disconnected or drained.

## 5. Configuring Nginx to Proxy WebSocket

With an Nginx reverse proxy, `Upgrade` and `Connection` are hop-by-hop headers and are not forwarded automatically like regular headers. The proxy must set them explicitly so the Spring backend knows the client wants to upgrade to WebSocket.

Example configuration for two Spring instances:

```nginx
http {
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    upstream spring_ws_nodes {
        least_conn;
        server app1.internal:8080;
        server app2.internal:8080;
    }

    server {
        listen 443 ssl;
        server_name ws.example.com;

        location /ws {
            proxy_pass http://spring_ws_nodes;

            # Explicit for compatibility with older Nginx versions.
            proxy_http_version 1.1;

            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

            proxy_read_timeout 75s;
            proxy_send_timeout 75s;
        }
    }
}
```

Key points to understand:

- `upstream` declares the Spring instances Nginx can choose from.
- `least_conn` distributes new connections based on the number of open connections.
- `proxy_http_version 1.1` enables WebSocket Upgrade on older Nginx versions. Since Nginx 1.29.7, HTTP/1.1 is the default for proxying, but declaring it explicitly keeps the configuration broadly compatible.
- `Upgrade` and `Connection` allow Nginx to establish the WebSocket tunnel.
- `Host`, `X-Forwarded-Proto`, and `X-Forwarded-For` help the application see the correct host, scheme, and client address behind the proxy. Trust forwarded headers only from proxies controlled by your system.
- `proxy_read_timeout` and `proxy_send_timeout` must be chosen according to heartbeats and the end-to-end idle policy.

If the endpoint has a different name, update `location` accordingly. If using SockJS, the `/ws/info` path and transport sub-URLs must also be routed to Spring. Do not route only the handshake request while missing HTTP fallback requests.

### SockJS HTTP Streaming

With SockJS XHR streaming, a response may be kept open to stream messages incrementally. Proxy buffering can cause messages to be held back instead of being delivered to the browser as soon as Spring sends them.

You can disable buffering for the SockJS endpoint:

```nginx
location /sockjs/ {
    proxy_pass http://spring_ws_nodes;
    proxy_http_version 1.1;

    proxy_buffering off;
    proxy_read_timeout 75s;
    proxy_send_timeout 75s;
}
```

A real-world configuration must forward all necessary headers and set CORS appropriately for the client's domain. `proxy_buffering off` supports HTTP streaming; it does not replace sticky routing for SockJS sessions.

## 6. Understanding Timeout Types Properly

A WebSocket connection can be closed by any component along the network path. Therefore, increasing timeouts only in Spring will not help if the load balancer or reverse proxy has a lower idle timeout.

Common timeout layers:

| Component | What Does the Timeout Control? | Symptoms When Too Low |
|---|---|---|
| Browser/client | Response wait time, internal timeout, or network policy | Client closes the socket itself or reports an error |
| CDN/load balancer | Idle time or maximum connection age | Connections are cut periodically or after a quiet interval |
| Reverse proxy | Inactivity reading/writing between proxy and backend | WebSocket closes when there is no traffic |
| Servlet container | Wait time or transport resources | Session is closed at the server layer |
| Spring WebSocket transport | Send limits, buffers, and message size | Session is closed due to slow client or oversized message |
| SockJS | Disconnect delay, heartbeat, and HTTP cache | Fallback session is treated as disconnected |
| STOMP broker | Heartbeat and inactivity detection between client/broker | Broker closes the TCP/STOMP connection |

### Nginx `proxy_read_timeout`

Nginx closes a connection by default if the upstream sends no data for 60 seconds. `proxy_read_timeout` measures the interval between two successive read operations from the upstream; it is not a maximum duration for the entire response.

For example, if Nginx is waiting for data from Spring and Spring sends no frames, heartbeats, or bytes for 60 seconds, Nginx may close the tunnel. You can increase `proxy_read_timeout`, but a more sustainable approach is configuring an appropriate heartbeat and setting the timeout higher than the heartbeat interval with a safety margin.

`proxy_send_timeout` applies to the interval between two successive write operations to the upstream. In a bidirectional connection, check both directions of traffic rather than tuning only a single directive.

### Load Balancer Idle Timeouts

Cloud load balancers, ingress controllers, firewalls, and NAT gateways may each have their own idle timeouts. Every provider has different defaults and measurement rules. Inspect the actual configuration of each layer and choose heartbeats/timeouts based on the lowest limit.

A connection can survive Nginx and still be closed earlier by a cloud load balancer. Therefore, map out timeouts across the entire path instead of checking only Spring's configuration.

### Timeouts Are Not Spring Send Limits

Spring WebSocket transport's `setSendTimeLimit` and `setSendBufferSizeLimit` control message sending and buffering for slow clients. `setMessageSizeLimit` limits inbound message size. They are not proxy idle timeouts.

Example configuration:

```java
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {

    registration
            .setSendTimeLimit(15_000)
            .setSendBufferSizeLimit(512 * 1024)
            .setMessageSizeLimit(128 * 1024);
}
```

The values above are illustrative starting points. Tune them according to message size, client read speed, and the memory budget per session. Setting the buffer too large can allow many slow clients to consume excessive memory.

## 7. Using Heartbeats to Keep Connections Alive and Detect Disconnects

A heartbeat is periodic data indicating that a connection is still alive. In STOMP applications, heartbeats can be negotiated between client and server during STOMP `CONNECT`. When there are no business messages, heartbeats still generate traffic so proxies do not consider the connection idle and both sides detect unresponsive peers.

Distinguish the types of heartbeats:

- **STOMP heartbeat:** newline frames sent between the STOMP client and server/broker at negotiated intervals.
- **SockJS heartbeat:** SockJS's own heartbeat frame, sent by Spring every 25 seconds by default when no other messages travel on the connection.
- **WebSocket Ping/Pong:** WebSocket protocol control frames that server or client can use to check the transport.
- **TCP keepalive:** a TCP/OS-level mechanism; not every intermediate proxy treats it as application traffic that resets idle timeouts.

When STOMP heartbeats are negotiated over STOMP-over-SockJS, the separate SockJS heartbeat is disabled. Therefore, verify exactly which heartbeat is active on the actual connection.

### Configuring Heartbeats for the Simple Broker

Spring's simple broker supports STOMP heartbeats when a `TaskScheduler` is configured. Example:

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    private TaskScheduler messageBrokerTaskScheduler;

    @Autowired
    public void setMessageBrokerTaskScheduler(
            @Lazy TaskScheduler taskScheduler) {
        this.messageBrokerTaskScheduler = taskScheduler;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[] {20_000, 20_000})
                .setTaskScheduler(this.messageBrokerTaskScheduler);

        registry.setApplicationDestinationPrefixes("/app");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws").withSockJS();
    }
}
```

This is an illustrative configuration for a single application instance using the simple broker. When deploying multiple nodes, replace the simple broker with an external broker relay as shown in Section 9.

In the heartbeat value:

- The first value is the interval at which the server sends heartbeats.
- The second value is the interval at which the server expects the client to send heartbeats.
- The unit is milliseconds.
- A value of `0` means no heartbeat in that direction.

The STOMP client must also support and negotiate heartbeats. With Spring's `WebSocketStompClient`, configure a `TaskScheduler` so the client sends heartbeats when there are no other messages. Browser STOMP clients need corresponding heartbeat settings according to the client library in use.

### Choosing Heartbeat Intervals and Proxy Timeouts

Suppose the server sends a heartbeat every 20 seconds and the proxy closes the connection if the upstream produces no data for 75 seconds. A 20-second interval allows a few delayed heartbeats before the proxy times out, without creating excessive traffic.

Reference example:

| Parameter | Illustrative Value |
|---|---:|
| Server STOMP heartbeat | 20 seconds |
| Client STOMP heartbeat | 20 seconds |
| Nginx `proxy_read_timeout` | 75 seconds |
| Nginx `proxy_send_timeout` | 75 seconds |

Do not copy these values verbatim for every system. Account for latency, jitter, JVM pause times, scheduler load, cloud load balancer timeouts, and dead-connection detection goals.

One crucial detail: `proxy_read_timeout` tracks data flowing from the upstream to the proxy. Heartbeats sent only from the browser to the server do not reset this upstream read timer. There must be traffic from the server to the client—such as server-sent STOMP heartbeats or server-initiated WebSocket Pings—to keep that read direction active.

Heartbeats that are too short increase traffic and scheduler overhead. Heartbeats that are too long can delay disconnect detection or fail to keep connections alive through proxies. Choose an interval with margin rather than setting it equal to the idle timeout.

## 8. Heartbeats Between Spring and an External STOMP Broker Are a Separate Path

When using a STOMP broker relay, there are at least two connection legs to monitor:

```text
Browser
   |
   | WebSocket + STOMP
   | client/server heartbeats
   v
Spring application
   |
   | TCP/STOMP to broker
   | broker relay heartbeats
   v
External STOMP broker
```

Heartbeats between the browser and Spring do not replace heartbeats between Spring and the broker. Each leg has its own timeouts, firewalls, and network path.

The STOMP broker relay creates:

- One system TCP connection used for messages originating from the server-side application.
- A separate TCP connection for each WebSocket client relayed to the broker.

The relay has heartbeats for the system connection; by default, both send and receive intervals are 10 seconds. When the broker connection drops, the relay attempts to reconnect periodically. Client connections created on behalf of WebSocket clients are separate connections; check connection limits and heartbeats according to your broker configuration.

If there are 20,000 WebSocket clients using the broker relay, the broker may have to hold roughly 20,000 client TCP connections plus the system connections of each Spring application instance. Check the broker's connection limits, file descriptors, memory, and throughput before scaling WebSocket counts high.

`BrokerAvailabilityEvent` indicates whether the relay's system connection is available or disconnected. Services can listen for this event to avoid sending messages when the broker is unavailable; when sending, you still need to handle `MessageDeliveryException`.

## 9. Scaling Multiple Spring Instances and User Destinations

Sticky sessions only route requests to one node. They do not automatically synchronize subscriptions or user registries across nodes.

Spring's simple broker holds subscriptions in each application instance's memory and is not suitable for clustering. When running multiple nodes, use an external STOMP broker via the broker relay so all instances send and receive messages through a shared broker.

Sample configuration:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("stomp-broker.internal")
            .setRelayPort(61613)
            .setUserRegistryBroadcast("/topic/simp-user-registry")
            .setUserDestinationBroadcast(
                    "/topic/unresolved-user-destination");
}
```

The two broadcast settings serve different roles:

- `setUserRegistryBroadcast` broadcasts the local user registry and receives registries from other nodes. This lets each node know which users are connected to other instances.
- `setUserDestinationBroadcast` broadcasts user destinations that the current node could not resolve so other nodes have a chance to handle them.

For example, Alice connects to node A, while a service on node B calls `convertAndSendToUser("alice", ...)`. If node B does not know Alice is connected on A, the destination may remain unresolved. User registry broadcast and unresolved destination broadcast help node B coordinate with node A through the shared broker.

Internal destinations such as `/topic/simp-user-registry` and `/topic/unresolved-user-destination` must be protected from untrusted clients. Do not allow clients to arbitrarily publish messages to these coordination channels.

The external broker also needs a policy for cleaning up inactive queues/destinations. Some brokers support auto-delete queues or purging inactive destinations; configure this according to your broker's documentation.

**Sticky sessions do not replace an external broker.** If two nodes each keep their own simple broker, clients on node A still do not automatically receive broadcasts published by a service on node B. Conversely, an external broker does not automatically migrate an open WebSocket to another node. The broker shares messages; each node still manages the WebSocket sessions directly connected to it.

## 10. Session Affinity, Spring Session, and Login State

If the application uses an HTTP session or `JSESSIONID` to authenticate the WebSocket handshake, ensure authentication works regardless of which instance receives the request.

There are two common approaches:

1. **Sticky sessions:** keep a client's subsequent HTTP requests on the same node. This is simple, but that node remains a dependency for the lifetime of the session.
2. **Shared session store:** use Spring Session with Redis or a shared store so nodes can read the HTTP session. Depending on application configuration, this allows requests after a reconnect to authenticate on a different node.

Sharing HTTP sessions with Spring Session does not migrate an open WebSocket TCP connection and does not automatically restore STOMP subscriptions. The client still has to reconnect and re-subscribe after the transport is lost.

For stateless applications using access tokens, each handshake or STOMP `CONNECT` can re-authenticate using the token. On reconnect, the client sends a fresh or still-valid token and is authenticated by the new node. Ensure authentication flows, CORS, and cookies/tokens behave consistently across the cluster.

SockJS's `sessionCookieNeeded` only affects transport selection when cookies are required. It is neither a shared session storage mechanism nor a load balancer affinity setting.

## 11. Graceful Shutdown and Reconnect During Deployments

A node may be removed from the pool due to deployment, scale-down, or failed health checks. Open WebSockets on that node will not automatically move to another node. When the node closes connections, clients must reconnect.

A controlled deployment process:

1. Mark the node as no longer accepting new connections via readiness/target health.
2. Stop accepting new handshakes while giving active connections a window to finish.
3. If the application supports it, send a maintenance notice so clients can prepare to reconnect.
4. Close remaining sessions before the process is terminated.
5. Clients reconnect with exponential backoff and jitter to prevent thousands of clients from reconnecting simultaneously.
6. Clients re-authenticate, create a new STOMP session, and re-register subscriptions.
7. If business requirements demand no missed messages, use sequence numbers, cursors, or inbox/outbox patterns so clients can fetch missed data.

Sticky sessions cannot keep clients on a dead node. Do not treat reconnecting to the same server as a delivery guarantee. WebSocket is a bidirectional transport; durability and message replay must be built at the application or broker layer.

In Kubernetes, set `terminationGracePeriodSeconds` high enough for the expected drain duration and coordinate readiness probes, `preStop` hooks, and ingress/load balancer draining. Specific durations depend on how long connections are allowed to linger and deployment policies.

## 12. Observability and Troubleshooting

Spring creates a `WebSocketMessageBrokerStats` bean when the STOMP message broker is enabled. This bean aggregates statistics about WebSocket sessions, STOMP frames, the broker relay, and channel executors; by default, it logs periodically at INFO level. Information can be exposed via JMX or integrated with the application's monitoring system.

Metrics to track:

| Metric | What to Watch For |
|---|---|
| Current WebSocket sessions per node | One node growing rapidly or severely skewed distribution |
| SockJS HTTP streaming/polling sessions | Unusual spike in fallbacks, possibly due to proxy blocking Upgrade |
| Connect failures and abnormal closes | Sudden spike after deployment or proxy changes |
| Send limit exceeded | Slow-reading clients, or send buffer/timeout set too low |
| Transport errors | Read/write errors, proxy resets, backend socket closures |
| STOMP `CONNECT`/`CONNECTED`/`DISCONNECT` | Unusual disconnect rate or missing `DISCONNECT` frames |
| Broker relay TCP connections | Connection count mismatching expected client sessions plus system connections |
| Inbound/outbound channel queues | Slow application processing or clients not consuming messages fast enough |
| Broker heartbeat failures | Spring and the broker failing to exchange heartbeats on time |

When connections drop after a fixed interval near 60 seconds, check Nginx `proxy_read_timeout`, cloud load balancer idle timeouts, and server heartbeats before changing code.

When SockJS fails intermittently with `session not found`, check whether `/info`, streaming, and polling requests are reaching the same backend. Verify cookie affinity or the `server-id` key in the URL.

When user messages only reach clients on the same node, check whether the simple broker or the external broker relay is in use. For multi-node setups, verify the shared broker and the two user registry/unresolved destination broadcast channels.

When the broker relay reports missing connections or heartbeat timeouts, compare WebSocket session counts against TCP connections to the broker and check broker limits.

## 13. Pre-Deployment Verification Tests

A deployment test suite should include:

1. **Handshake through proxy:** verify the HTTP Upgrade returns `101 Switching Protocols`, and the backend receives the expected path and required headers.
2. **Idle connection:** keep a client idle with no business traffic for longer than the proxy's shortest idle timeout; verify heartbeats keep the connection alive.
3. **Blocked heartbeat:** pause heartbeats or simulate a network drop to verify disconnects are detected within the expected window.
4. **SockJS fallback:** force clients to use XHR streaming and polling; verify requests of the same session are routed to the same node.
5. **Multi-node broadcast:** open clients on two different nodes, send a message through the external broker, and verify both receive it.
6. **Cross-node user destination:** connect a user to node A, send a notification from node B, and verify the user receives it.
7. **Node drain:** remove a node from the pool, close connections gracefully, and verify clients reconnect to a healthy node.
8. **Slow client:** throttle message reading to test send buffers, send timeouts, and isolation of slow clients.
9. **Broker restart:** stop and restart the broker, verify the system relay connection recovers, and confirm clients have an appropriate reconnect mechanism.

Do not test with just a single client on localhost. Proxies, load balancers, SockJS fallbacks, and the broker relay must be tested in a topology close to production.

## 14. Common Issues and Fixes

| Symptom | Common Cause | Fix |
|---|---|---|
| WebSocket handshake returns 400/426 or no 101 | Proxy does not forward `Upgrade` and `Connection` headers | Configure `Upgrade`, `Connection`, and HTTP/1.1 properly |
| Connection closes after ~60 seconds of inactivity | Nginx or LB idle timeout is lower than heartbeat | Check timeouts at every layer and enable server-to-client heartbeats |
| Browser sends heartbeats, yet proxy still closes connection | `proxy_read_timeout` is waiting for data from the upstream | Ensure the server sends heartbeats or Ping frames |
| SockJS works sometimes and fails session lookup other times | HTTP streaming/polling requests hit multiple instances | Enable affinity or consistent routing by session/`server-id` |
| Client reconnects but loses subscriptions | New STOMP session has not subscribed again | Store the subscription list on the client and re-subscribe after `CONNECTED` |
| User message does not reach another node | Using simple broker or local user registry only | Use external broker relay and configure registry/destination broadcasts |
| One node receives far too many connections | Round robin ignores long-lived connections or NAT skews IP hash | Use least connections/cookie affinity appropriately and monitor actual load |
| Deployments drop many clients at once | Node is terminated before draining | Readiness probes, connection draining, and reconnect backoff |
| Broker closes connection due to heartbeat | Heartbeat mismatch between Spring and broker, or delayed scheduler | Check relay/broker heartbeats and scheduler load |
| Server consumes excessive memory with slow clients | Send buffer too large or messages published faster than clients read | Cap buffer/time limits, throttle publishing, or disconnect slow clients |

## 15. Deployment Checklist

- [ ] Reverse proxy forwards `Upgrade` and `Connection` headers properly.
- [ ] WebSocket handshake returns `101 Switching Protocols`.
- [ ] `proxy_read_timeout` and LB timeouts align with server-to-client heartbeats.
- [ ] Heartbeats are configured at the right layers: browser–Spring, Spring–broker, and SockJS when needed.
- [ ] Client and server negotiate STOMP heartbeats when using STOMP.
- [ ] SockJS HTTP streaming/polling requests are routed consistently to the same logical session.
- [ ] Verified whether sticky sessions are needed for HTTP sessions/SockJS fallback.
- [ ] Not relying on sticky sessions to recover sockets or synchronize the broker across nodes.
- [ ] Multi-node deployments use an external broker relay and user registry/unresolved destination broadcasts as needed.
- [ ] Broker has sufficient capacity for all WebSocket client connections plus system connections.
- [ ] HTTP session/authentication state can be used on another node after reconnect if needed.
- [ ] Client reconnection uses backoff/jitter and re-subscribes.
- [ ] Nodes have readiness probes and graceful connection draining during deployments.
- [ ] Metrics exist for active sessions, abnormal closes, transport errors, send limits, and broker connections.
- [ ] Idle timeouts, SockJS fallback, multi-node broadcasts, and node failures have been tested.

## References

- [Spring Framework Reference — WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket.html)
- [Spring Framework Reference — SockJS Fallback](https://docs.spring.io/spring-framework/reference/web/websocket/fallback.html)
- [Spring Framework Reference — STOMP External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework Reference — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework Reference — STOMP User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework Reference — STOMP Monitoring](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html)
- [Spring Cloud Gateway — WebSocket Routing Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html)
- [Nginx — WebSocket Proxying](https://nginx.org/en/docs/http/websocket.html)
- [Nginx — Proxy Module and Timeout Directives](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [Spring Session — Common Configuration](https://docs.spring.io/spring-session/reference/configuration/common.html)
