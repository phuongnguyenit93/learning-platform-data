# CONNECT, CONNECTED, and session negotiation

> Goal: understand the two frames that open a STOMP session; know how the client and server negotiate the protocol version, virtual host, and heartbeat; distinguish a STOMP session from an HTTP/WebSocket connection; configure and monitor STOMP connections in Spring.

## 1. A STOMP session begins after the WebSocket handshake

STOMP (Simple Text Oriented Messaging Protocol) is a frame-based messaging protocol. It can run over TCP or over WebSocket. When it runs over WebSocket, establishing a connection involves two layers:

1. **HTTP/WebSocket handshake:** the client sends an HTTP Upgrade request; the server returns `101 Switching Protocols` if it accepts. The two sides can choose the STOMP subprotocol through the HTTP header `Sec-WebSocket-Protocol`.
2. **STOMP connection negotiation:** after the WebSocket is open, the client sends a `CONNECT` frame (or `STOMP`); the server returns `CONNECTED` if it accepts the STOMP session.

These two steps solve two different problems. The HTTP handshake establishes the WebSocket transport and chooses the subprotocol; `CONNECT`/`CONNECTED` negotiate the STOMP session that runs on that transport. A successfully opened WebSocket does not mean the STOMP session is ready.

General flow:

```text
Client                         Spring / STOMP server
  |                                      |
  |--- HTTP Upgrade -------------------> |
  |<-- 101 Switching Protocols --------- |
  |                                      |
  |--- CONNECT ------------------------> |
  |    accept-version                   |
  |    host                             |
  |    heart-beat                       |
  |                                      |
  |<-- CONNECTED ----------------------- |
  |    version                          |
  |    heart-beat                       |
  |    session (optional)               |
  |                                      |
  |<====== SEND / SUBSCRIBE / MESSAGE ==>|
  |                                      |
```

Spring publishes a `SessionConnectEvent` when it receives the `CONNECT` frame. Then, when the broker returns the `CONNECTED` frame, Spring publishes a `SessionConnectedEvent`; only from this point is the STOMP session considered fully established. The two events are useful for recording the moment the client starts connecting and the moment the broker confirms the connection.

## 2. STOMP frame structure

A STOMP frame consists of a command, headers, a blank line separating the headers from the body, and a NULL character terminating the frame:

```text
COMMAND
header-name:header-value
another-header:value

body (if the command allows it)
^@
```

`^@` in the example is how the STOMP documentation represents the NULL octet (`0x00`); in actual transmission, the client sends the real NULL byte, not the two characters `^` and `@`. The header line terminator uses LF or CRLF. Command and header names are case-sensitive.

`CONNECT` and `CONNECTED` carry only headers and have no body. A body is used only for certain frames such as `SEND`, `MESSAGE`, and `ERROR`. STOMP uses UTF-8 by default; the payload can be text or binary depending on `content-type` and `content-length`.

## 3. The client sends CONNECT

`CONNECT` is the first frame of a STOMP client after the transport is ready. In STOMP 1.2, the two required headers are:

- `accept-version`: the list of STOMP versions the client supports.
- `host`: the virtual host the client wants to connect to on the server.

Optional headers:

- `login`: the user name used to authenticate with the STOMP server.
- `passcode`: the password or credential, depending on the server's mechanism.
- `heart-beat`: the client's ability to send heartbeats and the heartbeat interval the client wants to receive.

Example CONNECT frame according to STOMP 1.2:

```text
CONNECT
accept-version:1.0,1.1,1.2
host:broker.example.net
heart-beat:10000,10000

^@
```

The example above shows that the client supports STOMP 1.0, 1.1, and 1.2; wants to connect to the virtual host `broker.example.net`; can send heartbeats at least every 10 seconds; and expects to receive data from the server at least every 10 seconds.

With STOMP 1.2, the client must send `accept-version` and `host`. If `accept-version` is absent, according to the specification the server understands that the client supports only STOMP 1.0. Therefore, new clients should explicitly declare the versions they actually support.

### How do CONNECT and STOMP differ?

STOMP 1.2 defines both the `CONNECT` and `STOMP` commands; a STOMP 1.2 server must handle `STOMP` the same way as `CONNECT`. Clients usually continue to use `CONNECT` for compatibility with older STOMP 1.0 servers. `STOMP` is beneficial when a system needs to clearly distinguish the STOMP protocol from other protocols at the TCP layer.

## 4. The server returns CONNECTED

If it accepts the connection, the server returns a `CONNECTED` frame. In STOMP 1.2, the required header is `version`, which indicates the STOMP version chosen for the entire session.

Optional headers:

- `heart-beat`: the heartbeat the server can send and expects to receive.
- `session`: the session identifier issued by the server.
- `server`: the server's name and version information.

Example:

```text
CONNECTED
version:1.2
heart-beat:5000,8000
session:sess-7f31a9
server:ExampleBroker/3.4

^@
```

`version:1.2` confirms that the two sides will use STOMP 1.2. `session` and `server` are optional headers; the client must work correctly even if the server does not send them. The session ID is a technical identifier issued by the server, not a username, an access token, or a business ID.

If the server does not accept the connection, the server usually returns an `ERROR` explaining the cause and then closes the connection. For example, the error can be due to no common version, a wrong virtual host, invalid credentials, or a server policy that rejects the client.

## 5. Negotiating the STOMP version

Starting with STOMP 1.1, the client uses `accept-version` to announce the list of versions it supports. The list is usually written in ascending order, separated by commas. The server chooses the highest version that both the client and the server support.

Example:

```text
CONNECT
accept-version:1.0,1.1,1.2
host:broker.example.net

^@

CONNECTED
version:1.2

^@
```

If the server supports 1.1 and 1.2, the chosen version is 1.2. After the `CONNECTED` frame, the client and server must follow the semantics of the chosen version for the rest of the session.

If the two sides have no common version, the server returns `ERROR` (usually with a `version` header listing the supported versions) and then closes the connection. The client should not continue to send `SEND` or `SUBSCRIBE` after this error.

For example, if the server supports only 1.2 but the client sends only `accept-version:1.0,1.1`: there is no common version, so the session is not established.

### STOMP version and the WebSocket subprotocol

When running over WebSocket, the HTTP header `Sec-WebSocket-Protocol` can contain values such as `v10.stomp`, `v11.stomp`, or `v12.stomp`. This is the subprotocol negotiation of the WebSocket handshake. The `accept-version` header and the `CONNECTED.version` response are the version negotiation at the STOMP layer.

The two mechanisms are related but do not replace each other. A connection can upgrade to WebSocket successfully and still fail at the STOMP `CONNECT` because of an incompatible version or because the server rejects the session.

## 6. The meaning of host, login, and passcode

### The host header

`host` in a STOMP `CONNECT` represents the virtual host the client wants to use on the messaging server. It can be the same as the hostname of the TCP endpoint, but it is not required to be. A broker can serve multiple virtual hosts at the same network address.

With the Spring broker relay, the `virtualHost` property is used as the value of the `host` header in the `CONNECT` frames that the relay forwards to the broker. This is useful when the hostname used to open the TCP connection differs from the virtual host the broker requires.

Do not confuse the STOMP `host` with the HTTP `Host` header in the WebSocket handshake. The HTTP `Host` routes the request to a web server; the STOMP `host` selects the virtual host at the messaging broker.

### The login and passcode headers

According to the STOMP protocol, `login` and `passcode` can be used to authenticate the client with the STOMP server, especially in the STOMP over TCP model. How authentication works and the account's permissions depend on the broker.

With STOMP over WebSocket in Spring, by default Spring ignores `login` and `passcode` on the `CONNECT` frame, because the user's identity is authenticated at the HTTP handshake (for example through Spring Security and cookies/sessions). When using the broker relay, the Spring relay automatically attaches the configured credentials for the client connections to the broker; the browser client does not need to send the broker credentials itself.

If the application needs token authentication in the STOMP CONNECT, it must implement its own authentication mechanism using a `ChannelInterceptor` and attach the `Principal` to the message/session as instructed by Spring. Do not treat sending an arbitrary `login` or `passcode` header as a successful authentication.

## 7. Heartbeat negotiation

Heartbeat helps both sides detect that the TCP/WebSocket connection is dead or no longer active. It is negotiated right in `CONNECT` and `CONNECTED` through the `heart-beat` header, which has two non-negative integers separated by a comma:

```text
heart-beat:<send>,<receive>
```

The meaning of the two values for the side that sends the frame:

- The first value is the minimum interval (in milliseconds) at which that side can send heartbeats out.
- The second value is the interval at which that side wants to receive data/heartbeats from the opposite side.
- A value of `0` in the first position means it cannot send heartbeats.
- A value of `0` in the second position means it does not require receiving heartbeats.
- If the `heart-beat` header is not sent, the specification treats it as equivalent to `heart-beat:0,0`.

Suppose the client declares `heart-beat:cx,cy` and the server returns `heart-beat:sx,sy`. The actual heartbeat interval is calculated separately for each direction:

| Direction | Condition for heartbeat to be active | Minimum send interval |
|---|---|---|
| Client → Server | `cx > 0` and `sy > 0` | `max(cx, sy)` milliseconds |
| Server → Client | `sx > 0` and `cy > 0` | `max(sx, cy)` milliseconds |

If either of the two values for that direction is 0, that direction has no heartbeat by agreement.

### Heartbeat calculation example

The client sends:

```text
CONNECT
accept-version:1.2
host:broker.example.net
heart-beat:10000,10000

^@
```

The server returns:

```text
CONNECTED
version:1.2
heart-beat:5000,8000

^@
```

We have:

- Client → Server: `max(10000, 8000) = 10000` ms, that is, at least every 10 seconds.
- Server → Client: `max(5000, 10000) = 10000` ms, that is, at least every 10 seconds.

If no business STOMP frame needs to be sent within the interval, the side sending the heartbeat must send a single frame terminator line (EOL, usually LF). If a data frame has already been transmitted within that interval, that data also proves the connection is still active and no empty heartbeat needs to be sent.

The receiving side can consider the connection dead if it receives no data within the required time window. However, a tolerance is needed for the scheduler, network jitter, GC pauses, and machine load; do not close the connection just because of a delay of a few milliseconds.

Heartbeat only checks the liveness of the transmission path. It does not confirm that a business message has been processed, and it does not replace `ACK`, `RECEIPT`, or a completion state in the database.

## 8. CONNECTED, RECEIPT, and ERROR are different

| Frame | Meaning |
|---|---|
| `CONNECTED` | The server accepts `CONNECT` and confirms that the STOMP session has been established with the chosen version |
| `RECEIPT` | The server confirms it has processed a client frame that requested a receipt; it does not mean all downstream work has completed |
| `ERROR` | The server reports a protocol error or a processing error; according to STOMP 1.2 the server closes the connection after sending ERROR |

A client can use the `receipt` header on frames such as `SEND`, `SUBSCRIBE`, or `DISCONNECT` to request a `RECEIPT`. The specification does not allow the client to request a receipt on `CONNECT`; `CONNECTED` itself is the success response for the STOMP connection process.

A `RECEIPT` indicates that the server has processed the corresponding frame and is a cumulative confirmation that the earlier frames were received over the stream. However, those frames may not yet have been fully processed at the business layer.

## 9. Configuring STOMP in Spring

Spring provides STOMP over WebSocket support in the two modules `spring-messaging` and `spring-websocket`. The basic configuration uses `@EnableWebSocketMessageBroker`, registers an endpoint, and chooses a message broker:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompWebSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

Here `/ws` is the HTTP URL used to perform the WebSocket handshake. STOMP frames are sent after the transport has been opened. Destinations starting with `/app` are routed to `@MessageMapping` methods; the `/topic` and `/queue` destinations are handled by the simple broker.

The `/topic` and `/queue` prefixes in Spring's simple broker are naming conventions. When using an external broker, the destination syntax and semantics depend on the actual broker.

### Enabling heartbeat for the simple broker

The simple broker can send and receive STOMP heartbeats when a `TaskScheduler` is configured. For example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Bean
ThreadPoolTaskScheduler stompHeartbeatScheduler() {
    var scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(1);
    scheduler.setThreadNamePrefix("stomp-heartbeat-");
    return scheduler;
}
```

Then attach the scheduler and the heartbeat interval to the simple broker:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue")
            .setHeartbeatValue(new long[] {10000, 10000})
            .setTaskScheduler(stompHeartbeatScheduler());
}
```

The heartbeat array has two values in the order of what the server sends and what the server wants to receive, in milliseconds. You need to ensure that the scheduler is managed by Spring and that a new scheduler is not created for each configuration call. When there is no `TaskScheduler`, the simple broker cannot perform heartbeat in this configured way.

The simple broker is suitable for simple applications and stores subscriptions in memory. When you need full broker features, clustering capability, or broker-specific ACK/receipt semantics, consider the STOMP broker relay and check the specific features of the broker.

## 10. Broker relay, virtual host, and CONNECT credentials

When using an external STOMP broker such as RabbitMQ or ActiveMQ, Spring can act as a relay:

- One system TCP connection is used for messages originating from the server-side application.
- Each WebSocket client has its own TCP connection created by the relay to the broker.
- The relay can be configured with `systemLogin`/`systemPasscode` for the system connection and `clientLogin`/`clientPasscode` for the connections that represent clients.
- The relay's `virtualHost` is placed in the `host` header of the `CONNECT` frame sent to the broker.
- The relay manages heartbeat on the system connection and automatically tries to reconnect when the broker connection is lost.

Example broker relay configuration (the credential variables must come from the environment's security configuration):

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.internal")
            .setRelayPort(61613)
            .setClientLogin(clientLogin)
            .setClientPasscode(clientPasscode)
            .setSystemLogin(systemLogin)
            .setSystemPasscode(systemPasscode)
            .setVirtualHost("orders-vhost");
}
```

In the example, `clientLogin`, `clientPasscode`, `systemLogin`, and `systemPasscode` are configuration values injected from secrets/configuration management. Do not hardcode broker passwords in source code. The Spring relay automatically attaches the configured credentials to the CONNECT sent to the broker; the browser client does not need to send the broker credentials itself.

## 11. Monitoring the session lifecycle in Spring

Spring publishes several application events that help observe the connection process:

| Event | When | Meaning |
|---|---|---|
| `SessionConnectEvent` | When Spring receives the STOMP `CONNECT` frame | The client begins requesting to open a STOMP session |
| `SessionConnectedEvent` | After the broker returns the `CONNECTED` frame | The STOMP session has been established |
| `SessionDisconnectEvent` | When the STOMP session ends | The client sends DISCONNECT or the WebSocket session is closed |

You can use `SessionConnectEvent` to record the connection request, and `SessionConnectedEvent` to measure the negotiation time until the session is ready. `SessionDisconnectEvent` can be published more than once in some situations; the cleanup handler must be idempotent.

Do not treat the session ID as a user identifier. Use `Principal` to identify the authenticated user; use the session ID to trace a specific connection. When reconnecting, the client may receive a new session ID.

## 12. The Spring client and heartbeat

Spring provides `WebSocketStompClient` for STOMP over WebSocket and STOMP over TCP. To enable heartbeat on the client side, configure a `TaskScheduler` for the client:

```java
import org.springframework.scheduling.TaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

WebSocketStompClient stompClient = new WebSocketStompClient(
        new StandardWebSocketClient()
);
stompClient.setTaskScheduler(taskScheduler);
```

When a scheduler is present, the client can send heartbeats when there is no other data and monitor read inactivity. The default interval in the current Spring documentation is 10 seconds for write inactivity and 10 seconds for read inactivity; the application can customize it according to the network, broker, and SLA.

When the session is established, `StompSessionHandler.afterConnected(...)` receives the `StompSession` and the headers of the `CONNECTED` frame. This is the appropriate place to register subscriptions and start sending messages after the connection has succeeded.

## 13. Common mistakes with CONNECT and CONNECTED

- **Confusing the WebSocket 101 with the STOMP CONNECTED:** the transport is open but the STOMP session may not yet be accepted.
- **Missing `accept-version` on a new client:** the server understands that the client supports only STOMP 1.0 according to the specification.
- **No common version:** the server returns ERROR and closes the connection; the client needs to report a clear compatibility error.
- **Confusing the STOMP `host` with the HTTP Host:** one value selects the broker's virtual host, the other routes the HTTP request.
- **Treating `session` as a required header:** the server is allowed not to send a session ID in `CONNECTED`.
- **Using the session ID as the user ID:** the session ID only identifies the connection; it does not prove identity or permissions.
- **Confusing `login`/`passcode` with Spring's HTTP authentication:** Spring STOMP over WebSocket ignores these headers by default.
- **Calculating the heartbeat in the wrong direction:** the client-send direction uses `max(client-send, server-receive)`; the server-send direction uses `max(server-send, client-receive)`.
- **Setting the heartbeat to 0 but expecting idle connection detection:** a value of 0 disables heartbeat in the corresponding direction.
- **Using heartbeat as a business ACK:** heartbeat only indicates that the transmission path is still active.
- **Enabling heartbeat without configuring a scheduler:** the simple broker or STOMP client has no scheduler to emit periodic heartbeats.
- **Not handling the ERROR frame:** the server may close the socket immediately after sending ERROR.
- **Registering subscriptions before CONNECTED:** the session is not ready; wait for the callback/event that confirms the connection.
- **Assuming CONNECTED lists all of the broker's capabilities:** the chosen protocol version does not describe every extension or broker-specific delivery semantics.

## 14. Testing session negotiation

You should test the following scenarios with the actual broker/client versions:

1. The client and server both support STOMP 1.2: CONNECTED returns `version:1.2`.
2. The client supports 1.0/1.1/1.2, the server supports 1.1/1.2: the server chooses the highest common version, 1.2.
3. The client does not send `accept-version`: confirm that the server applies 1.0 semantics according to the specification.
4. The two sides have no common version: the server returns ERROR and closes the connection.
5. The client/server disables heartbeat in one direction with a value of 0: that direction does not send heartbeats.
6. Both sides enable heartbeat: confirm the actual interval according to the max calculation for each direction.
7. No business messages for a long time: the heartbeat EOL still keeps the connection active.
8. The broker loses the connection: the client receives a transport error/heartbeat timeout and reconnects according to the policy.
9. Wrong virtual host: the broker rejects CONNECT with an appropriate error.
10. Wrong credentials: confirm that HTTP authentication or broker authentication works correctly with the topology in use.
11. Spring receives CONNECT but the broker has not yet returned CONNECTED: mark the session ready only after `SessionConnectedEvent`.
12. Session disconnect or reconnect: a new session ID is handled as a new connection and cleanup does not repeat side effects.

When investigating, record the STOMP version the client proposed, the version the server chose, the heartbeat of both sides, the time of CONNECT/CONNECTED/ERROR, the WebSocket close status, and the cause returned by the broker. Do not write the `passcode`, tokens, or authentication data to logs.

## 15. STOMP connection handling procedure

1. Open a WebSocket to the correct endpoint and negotiate the STOMP subprotocol at the HTTP handshake.
2. Send `CONNECT` with the correct `accept-version` and `host`; add heartbeat if the client supports it.
3. Wait for `CONNECTED`; read the chosen `version` and the heartbeat the server returned.
4. Calculate the heartbeat interval separately for client→server and server→client; enable the corresponding scheduler.
5. Only after the session is confirmed, send `SUBSCRIBE` or `SEND`.
6. Handle `ERROR`, transport close, and heartbeat timeout with an explicit connection state.
7. When reconnecting, negotiate a new session and re-register the necessary subscriptions.
8. Use the `Principal`/authentication context to identify the user; use the session ID to trace the connection.
9. Test versions, virtual host, credentials, heartbeat, broker restart, and disconnect.

## 16. Conclusion

`CONNECT` is the client's proposal to open a STOMP session; `CONNECTED` confirms that the server accepts the session and announces the chosen protocol version. `accept-version` lets the two sides choose the highest common version; `host` selects the virtual host; `session` and `server` are optional metadata.

Heartbeat is negotiated in two independent directions. The client sends according to `max(client-send, server-receive)` and the server sends according to `max(server-send, client-receive)` when both sides enable the corresponding direction. In Spring, you need to distinguish the HTTP/WebSocket handshake from the STOMP CONNECT, use `SessionConnectedEvent` to determine that the session is ready, configure a scheduler for heartbeat, and understand how Spring handles credentials when using WebSocket or the broker relay.

## References

- [STOMP Protocol Specification 1.2 — Connecting, Protocol Negotiation and Heart-beating](https://stomp.github.io/stomp-specification-1.2.html)
- [Spring Framework Reference — STOMP Overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html)
- [Spring Framework Reference — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework Reference — Simple Broker and Heartbeats](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework Reference — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework Reference — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework Reference — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework Reference — Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)