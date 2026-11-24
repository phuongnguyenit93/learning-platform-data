# TaskScheduler and Simple Broker Heart-Beats

In Spring WebSocket/STOMP, the simple broker can exchange heartbeats with each STOMP client to recognize whether the session connection is still active and detect when a client has stopped sending data. To do this, the broker needs a `TaskScheduler` that runs periodically. When configuring a `TaskScheduler` for `enableSimpleBroker(...)`, Spring enables heartbeat capability; the application can also explicitly set the two intervals using `setHeartbeatValue(...)`.

Heartbeats help detect connections that are hung or dropped without a notification frame. They are not business messages, do not replace ACK/RECEIPT, and do not turn the simple broker into a message broker with durable storage.

## 1. The Simple Broker and the Role of Heartbeats

The simple broker is a built-in message broker in Spring Messaging. It receives subscribe requests, stores subscription information in memory, and forwards messages to clients whose subscriptions match the destination. Common configuration:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

Clients send messages to an application destination such as `/app/chat`; a controller processes the message and can then send the result to a broker destination such as `/topic/chat`. The simple broker holds subscriptions for connected sessions to distribute messages.

A WebSocket connection can be lost because a device sleeps, a network switches, a proxy closes an idle connection, a client process stops, or the link fails. Sometimes the application does not receive a socket-close event immediately. Without other activity, the broker may continue holding subscriptions for a session that is no longer usable.

A heartbeat is a periodic signal at the STOMP layer that helps both ends know the other is active. When there is no regular STOMP frame to send, the sender emits an end-of-line (EOL, typically an LF newline character). When other STOMP data passes over the connection, that data is also considered activity and can substitute for a separate heartbeat within the corresponding interval.

In Spring's simple broker, heartbeats operate in two directions:

- The server sends a heartbeat to the client when the server has sent no other message within the negotiated interval.
- The server monitors data sent back by the client. If the client sends no data within the requested interval, the simple broker performs disconnect handling and cleans up that session's subscriptions.

A heartbeat contains no destination, business payload, or chat content. The client does not receive it as a regular `MESSAGE` frame on a subscription.

## 2. What Does TaskScheduler Do?

`TaskScheduler` is Spring's abstraction for scheduling tasks over time. For the simple broker, the scheduler provides the timer mechanism for the heartbeat task. The periodic task checks the read/write state of sessions:

- If a session is overdue for receiving data from the client according to the negotiated heartbeat interval, the broker handles the session as a disconnected connection.
- If a session is overdue for sending data from the server, the broker emits an empty heartbeat down to the client.
- If regular messages have been exchanged, the corresponding activity timestamp is updated and an extra heartbeat does not need to be sent right then.

The scheduler thus supports both sending heartbeats and checking client liveness. It does not automatically send messages to a destination and does not replace the application's business scheduler.

### Defaults When Unconfigured

According to the API of `SimpleBrokerRegistration` and `SimpleBrokerMessageHandler`:

- Without a `TaskScheduler`, the default heartbeat is `[0, 0]`, meaning do not send and do not require heartbeats.
- When a `TaskScheduler` is set without specifying custom values, Spring defaults heartbeats to `[10000, 10000]` (milliseconds).
- If non-zero heartbeat values are set without providing a scheduler, the simple broker cannot run the periodic task; such configuration is invalid and the broker will fail on startup.

Therefore, to enable heartbeats, configure both the scheduler and the two desired values, or configure the scheduler and accept the 10-second default in each direction.

## 3. Configuring Heartbeats for the Simple Broker

Spring allows using the scheduler already declared in the built-in WebSocket configuration. When injecting this scheduler into `WebSocketMessageBrokerConfigurer`, use `@Lazy` to avoid a circular dependency between the internal WebSocket configuration and the application's configuration class.

The following example asks the server to send a heartbeat at least every 10 seconds and expects the client to send data every 20 seconds:

~~~java
package com.example.messaging;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

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
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableSimpleBroker("/topic/", "/queue/")
                .setHeartbeatValue(new long[] {10_000, 20_000})
                .setTaskScheduler(this.messageBrokerTaskScheduler);
    }
}
~~~

Key points to understand in the example:

- `enableSimpleBroker("/topic/", "/queue/")` enables the simple broker for destinations with the corresponding prefixes.
- `setHeartbeatValue(new long[] {10_000, 20_000})` sets the server-send interval and the interval at which the server expects the client to send, in milliseconds.
- `setTaskScheduler(...)` provides the scheduler for the simple broker to execute heartbeat tasks.
- `@Lazy` defers resolving the pre-configured scheduler until needed, avoiding a circular dependency in the WebSocket configuration.

If you do not need custom intervals, you can omit `setHeartbeatValue(...)`; when a scheduler is present, the simple broker's default is 10,000 ms for both values.

### Using an Application-Declared Scheduler

An application can also declare its own `ThreadPoolTaskScheduler` bean, especially when it wants control over thread count, thread names, or operational settings. Example:

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
public class MessagingSchedulerConfig {

    @Bean
    public ThreadPoolTaskScheduler messageBrokerTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }
}
~~~

Then inject the bean by name using `@Qualifier("messageBrokerTaskScheduler")` and pass it into `setTaskScheduler(...)` in the broker configuration. When the scheduler is a Spring bean, the container manages its initialization and shutdown lifecycle. Do not create a new scheduler per client or per message.

If the application has multiple beans of type `TaskScheduler`, use `@Qualifier` to select the right bean. If using Spring's built-in scheduler, follow the `@Lazy` pattern shown earlier.

## 4. Meaning of setHeartbeatValue

`setHeartbeatValue` accepts an array of exactly two non-negative numbers:

~~~java
.setHeartbeatValue(new long[] {10_000, 20_000})
~~~

The two elements are interpreted from the server's perspective:

| Element | Meaning | Example |
|---|---|---|
| First element | Minimum interval at which the server can send outgoing heartbeats | `10_000` ms = 10 seconds |
| Second element | Interval at which the server expects to receive data/heartbeats from the client | `20_000` ms = 20 seconds |

A value of `0` means disabling heartbeats in the corresponding direction. For example:

- `[10000, 10000]`: the server can send every 10 seconds and expects the client to send every 10 seconds, before considering negotiation with the client.
- `[10000, 0]`: the server can send heartbeats; the server does not require the client to send heartbeats.
- `[0, 20000]`: the server does not send heartbeats; the server requires the client to send data/heartbeats every 20 seconds.
- `[0, 0]`: disables heartbeats in both directions.

These numbers are milliseconds, not seconds. Writing `10` means 10 milliseconds, not 10 seconds.

The array must have exactly two elements and each element must be non-negative. Negative values or an incorrectly sized array constitute an invalid configuration.

## 5. Heartbeat Negotiation in the STOMP Protocol

Spring's configuration represents the server's capability and preference. The actual heartbeat intervals also depend on the header the client sends when connecting. STOMP 1.1 and later use the `heart-beat` header in the first two frames of the session:

~~~text
CONNECT
accept-version:1.2
host:localhost
heart-beat:5000,10000

^@

CONNECTED
version:1.2
heart-beat:10000,20000

^@
~~~

The two pairs of numbers have the same meaning on both client and server:

- First number: the minimum interval the sender can guarantee for sending outgoing heartbeats.
- Second number: the interval at which the sender wants to receive heartbeats from the other side.
- `0`: the sender cannot send heartbeats or does not require receiving heartbeats, depending on the number's position.

Notation:

- The client declares `cx, cy` in `CONNECT`.
- The server declares `sx, sy` in `CONNECTED`.

Both directions are calculated independently:

~~~text
Client -> Server:
  No heartbeat if cx = 0 or sy = 0
  If both are non-zero: actual interval = max(cx, sy)

Server -> Client:
  No heartbeat if sx = 0 or cy = 0
  If both are non-zero: actual interval = max(sx, cy)
~~~

For example, the client sends `heart-beat:5000,10000`, and the server returns `heart-beat:10000,20000`:

- Client → server: `max(5000, 20000) = 20000` ms, or 20 seconds.
- Server → client: `max(10000, 10000) = 10000` ms, or 10 seconds.

Therefore, `setHeartbeatValue([10000, 20000])` does not guarantee every client receives heartbeats every 10 seconds and sends every 20 seconds. Those are the two values the server proposes for negotiation. If a client does not support or does not request one direction of heartbeats, that direction may be disabled.

If the client does not send a `heart-beat` header, the protocol treats it as `heart-beat:0,0`; in that case, no heartbeats are negotiated for that session.

## 6. The Client Must Also Enable Heartbeats

Configuring a scheduler on the server alone is not enough to establish bidirectional heartbeats. The client must advertise its send capability and receive preference in `CONNECT`. With STOMP.js, heartbeat values can be configured when creating the client:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  heartbeatIncoming: 10_000,
  heartbeatOutgoing: 10_000,
  reconnectDelay: 5_000
});

client.onConnect = () => {
  client.subscribe("/topic/notifications", message => {
    console.log(message.body);
  });
};

client.activate();
~~~

In STOMP.js:

- `heartbeatOutgoing` is the interval at which the client wants to send heartbeats to the server.
- `heartbeatIncoming` is the interval at which the client expects to receive heartbeats from the server.
- Values are in milliseconds.
- Heartbeats are only exchanged when both sides negotiate a non-zero value for that direction.

If using Spring's `WebSocketStompClient` on the client side, configure a `TaskScheduler` for the client and call `setDefaultHeartbeat(...)` when adjusting default intervals. The client-side scheduler and the simple broker's scheduler are two configurations at the two ends of the connection; each side is responsible for its own tasks.

## 7. What Do Heartbeats Actually Do During a Session?

Suppose client and server have negotiated a 10-second heartbeat in both directions.

1. The client sends `CONNECT` with its send capability and receive preference.
2. The server replies `CONNECTED` with the server's two heartbeat values.
3. Spring computes the actual interval for each direction according to STOMP rules.
4. The simple broker stores timestamps of when data was received from and sent to the session.
5. The task scheduled by `TaskScheduler` periodically inspects the sessions.
6. If the server has sent no other message within the write deadline, the broker sends an empty heartbeat.
7. If the server has received no client data within the negotiated read deadline, the broker performs disconnect handling and removes the session from subscription state.

Any regular STOMP frame exchanged on the connection demonstrates activity from the sender. Therefore, a session sending messages frequently does not need extra empty heartbeats every cycle. Heartbeats are primarily meaningful when the connection has no business traffic.

At the wire protocol level, a heartbeat is an empty EOL line, typically an LF byte (`0x0A`). It is not a `MESSAGE` frame, has no `destination` header, and does not appear as an application payload. In Spring's code, the internal message type used to represent this signal is `SimpMessageType.HEARTBEAT`.

When a client sends no data within the negotiated interval, the simple broker triggers disconnect handling for the session. This allows the broker to remove orphaned subscriptions from the registry. Heartbeat detection is not proof that prior business logic was processed successfully; it only indicates the liveness state of the transport/session per protocol rules.

## 8. Choosing Intervals and Operating the Scheduler

Heartbeat intervals that are too short increase scheduler wakeups and control traffic. Intervals that are too long cause the application to detect dead connections more slowly. When choosing values, consider:

- Idle timeouts of reverse proxies, load balancers, ingress controllers, or firewalls along the path.
- Actual client network latency and jitter.
- Time taken by mobile devices to switch between Wi-Fi and cellular networks or enter battery-saving mode.
- Number of concurrent connections and scheduler processing capacity.
- How long the application can tolerate an unreachable session before cleaning up subscriptions.

If a proxy closes connections after 60 seconds with no data, the actual heartbeat interval should be lower than that timeout with sufficient safety margin. Do not look only at the server-side configured value: the result negotiated with the client determines the final exchange interval.

### Thread Management

If using a dedicated `ThreadPoolTaskScheduler`, choose the pool size based on load and the number of scheduled tasks in the application. Do not run long or blocking business tasks on the heartbeat scheduler. A blocked task can delay heartbeats and cause healthy sessions to be judged as disconnected.

With the simple broker, the heartbeat task is shared to check active sessions. You do not need to create a separate thread or scheduler per user. Monitor logs, connected session counts, disconnect counts, and thread health during real operation.

When the application stops, Spring manages the lifecycle of scheduler beans. If you create a scheduler outside the Spring container, the application must ensure it is initialized and shut down properly; that approach is usually unnecessary in standard Spring configurations.

## 9. Distinguishing Heartbeats from Other Mechanisms

| Mechanism | Purpose | Does It Replace STOMP Heartbeat? |
|---|---|---|
| STOMP heartbeat | Bidirectional liveness check at the STOMP layer | This is the mechanism being configured |
| WebSocket Ping/Pong | Liveness check at the WebSocket transport layer | No; different layer and management |
| TCP keepalive | OS-level TCP connection check per socket settings | No; intervals are usually long and OS-dependent |
| STOMP RECEIPT | Confirms the server processed a frame requesting a receipt | No; confirms frame processing, not periodic connection checks |
| STOMP ACK/NACK | Confirms the client consumed or rejected a message | No; relates to message processing |
| Application event/ping | Checks business logic or application state | No; this is an application-defined message |

In browsers, JavaScript generally cannot directly create WebSocket Ping/Pong control frames. STOMP heartbeats are STOMP protocol data sent over the connection, so applications can configure them through the STOMP library.

Do not use heartbeats to prove that a message was written to a database, processed by a consumer, or will be re-sent after a reconnect. Those requirements need ACK, persistence, retries, or an appropriate broker.

## 10. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check or Fix |
|---|---|---|
| No heartbeats seen from server | `TaskScheduler` not attached, heartbeat value is 0, or client did not request receiving | Check the scheduler, `setHeartbeatValue`, and the `heart-beat` header in `CONNECTED`. |
| Broker fails at startup | Non-zero heartbeat set without a scheduler | Pass a `TaskScheduler` into `setTaskScheduler`. |
| Clients disconnected even though network is up | Scheduler blocked, negotiated interval too short, or client paused | Check logs, scheduler load, pause duration, and actual bidirectional intervals. |
| Connection closed by proxy when idle | Actual heartbeat longer than proxy idle timeout | Reduce negotiated interval and verify heartbeat traffic actually traverses the proxy. |
| Server has scheduler but client sends no heartbeats | Client does not advertise send capability or server does not require receiving | Check `heart-beat` in CONNECT/CONNECTED and client configuration. |
| Wrote `10000` thinking it was 10 milliseconds | Unit confusion | Values are in milliseconds: 10,000 ms = 10 seconds. |
| Confusing heartbeats with subscription messages | Heartbeat is an empty EOL at the STOMP layer | Do not look for heartbeats as a `/topic` destination body. |
| Using heartbeats to confirm message processing | Confusing connection liveness signals with ACK/RECEIPT | Use an appropriate acknowledgment mechanism for messages and business logic. |
| Multiple TaskSchedulers injecting the wrong bean | Multiple beans of the same type exist | Use `@Qualifier` or use the built-in scheduler with `@Lazy`. |

## 11. Testing Checklist

When enabling heartbeats for the simple broker, verify using a real STOMP client or integration test:

1. Confirm the application starts with the scheduler successfully injected.
2. Connect with a client sending a non-zero `heart-beat` header and confirm the server returns values in `CONNECTED`.
3. Compute the actual heartbeat intervals for both directions using the STOMP `max` rule.
4. Leave the connection idle and observe empty heartbeats on the transport or in client-side frame logs.
5. Send messages regularly to confirm actual STOMP data also keeps the connection considered active.
6. Stop sending data from the client in a controlled test environment and confirm the simple broker performs disconnect handling after the appropriate timeout.
7. Stop the scheduler or use an invalid configuration in a configuration test to recognize the missing-scheduler error.
8. Test through a real proxy or load balancer if the deployment environment enforces idle timeouts.
9. Confirm reconnect creates a new session and new subscriptions per application logic; do not assume heartbeats restore old subscriptions automatically.

Test both directions. A client may receive heartbeats regularly without sending heartbeats; that case only proves the server → client direction is working. Similarly, a client sending regularly without receiving responses does not prove the server → client direction is healthy.

## References

- [Spring Framework Reference — Simple Broker](https://docs.spring.io/spring-framework/reference/6.1/web/websocket/stomp/handle-simple-broker.html): role of the simple broker, `TaskScheduler` configuration, and heartbeat-enabling example.
- [Spring Framework 6.1.11 Javadoc — SimpleBrokerRegistration](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/simp/config/SimpleBrokerRegistration.html): `setHeartbeatValue`, `setTaskScheduler`, and default values.
- [Spring Framework 6.1.11 Javadoc — SimpleBrokerMessageHandler](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/simp/broker/SimpleBrokerMessageHandler.html): scheduler and heartbeat configuration on the broker handler.
- [Spring Framework Reference — STOMP Client](https://docs.spring.io/spring-framework/reference/6.1/web/websocket/stomp/client.html): client-side heartbeat configuration for `WebSocketStompClient`.
- [STOMP 1.2 Specification — Heart-beating](https://stomp.github.io/stomp-specification-1.2.html#Heart-beating): `heart-beat` header, bidirectional negotiation rules, and EOL signal.
