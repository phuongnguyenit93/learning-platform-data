# Keepalive and Detecting Lost Transport Connections

## Objectives

After this lesson, you will be able to:

- Explain why a TCP or WebSocket connection can appear to remain open even when the network path has failed.
- Describe the role of the **KEEPALIVE** frame in the lifecycle of an RSocket connection.
- Distinguish **keepAlive interval**, **maxLifetime**, and a request timeout.
- Configure keepalive through **RSocketRequester** in Spring and observe connection close events.
- Choose appropriate parameters and handle errors without blindly retrying.

## 1. Why Detect Lost Connections?

RSocket maintains a transport connection to carry multiple concurrent streams. A connection may be idle because the application has not sent requests yet, but that does not mean the connection is dead. Conversely, the operating system may still view the socket as open even though one peer lost power, a device switched networks, a router dropped NAT state, or the path became black-holed.

There are two situations to distinguish:

1. **Explicit connection closure:** TCP receives FIN/RST or WebSocket emits a close/error signal. The transport can notify the application immediately.
2. **Half-open connection or silent path:** no explicit close signal arrives. The application sends data without receiving a response; if there is no traffic, detection can be delayed for a very long time.

If an RSocket connection is lost, multiple streams sharing that connection can fail together. Therefore, the application needs to know when a connection is no longer usable to release resources, update client state, and decide whether to reconnect.

## 2. How Does Keepalive Work in RSocket?

Keepalive is a heartbeat mechanism at the **connection level** of the RSocket protocol. It generates periodic control frames even when there are no business requests. Its purpose is to verify that the peer can still exchange frames over the connection.

The parameters are declared in the **SETUP** frame:

- **Time Between KEEPALIVE Frames:** how often the client intends to send **KEEPALIVE** frames.
- **Max Lifetime:** how long the client allows going without receiving a keepalive response from the server before considering the server disconnected.

A typical cycle proceeds as follows:

1. The client opens the transport and sends a **SETUP** frame containing the interval and max lifetime.
2. Once the connection is established, the client sends **KEEPALIVE** frames at the configured interval.
3. The frame sent by the client has the **RESPOND** flag enabled to request a reply from the peer.
4. The server receives the frame and sends back a **KEEPALIVE** frame with the **RESPOND** flag disabled. The frame's data portion is echoed back.
5. The client continues tracking the time since a frame was received from the server. If **maxLifetime** is exceeded without receiving a valid keepalive, the client considers the connection dead.

~~~mermaid
sequenceDiagram
    participant C as RSocket client
    participant S as RSocket server
    C->>S: SETUP(interval, maxLifetime)
    loop Every interval
        C->>S: KEEPALIVE (RESPOND = true)
        S-->>C: KEEPALIVE (RESPOND = false, echo data)
    end
    Note over C: No keepalive received within maxLifetime
    Note over C: Consider peer disconnected
~~~

Some important frame details:

- **KEEPALIVE** always uses **Stream ID = 0**, because it applies to the entire connection rather than a specific request stream.
- The **RESPOND** flag indicates whether the frame requires a response. When receiving a frame with this flag set, the peer must return a frame with the **RESPOND** flag disabled and echo the data.
- The **Last Received Position** field supports the resumption mechanism. When resumption is not used, this field is set to 0.
- The client is the party that sends periodic keepalives according to the protocol. The server can also proactively send keepalives in certain cases when required by the application.

Keepalive does not require a route, business payload, or a **@MessageMapping** method. It is a protocol frame handled at the RSocket layer.

## 3. Distinguishing interval and maxLifetime

These two parameters solve two different problems:

| Parameter | Meaning | When set too low | When set too high |
| --- | --- | --- | --- |
| **interval** | How often the client sends keepalive | Increases control frames, CPU, and battery consumption | May not generate traffic frequently enough to pass intermediate network idle timeouts |
| **maxLifetime** | Time waiting for keepalive from the peer before considering the connection dead | Prone to false positives during network latency, JVM pauses, or brief signal drops | Slow detection of broken connections, holding resources and failed streams longer |

RSocket Java defaults to **interval = 20 seconds** and **maxLifetime = 90 seconds**. These are library defaults, not the optimal configuration for every environment. The API recommends setting max lifetime wide enough to allow multiple missed heartbeats before concluding the connection is dead.

When choosing values, consider:

- Normal network latency and latency spikes.
- How long the JVM may pause due to garbage collection or CPU saturation.
- Idle timeouts of load balancers, proxies, firewalls, and NATs.
- Client type: server-to-server can usually send frequent heartbeats; mobile devices must balance fast detection against battery life. The RSocket specification mentions 500 ms as a reasonable interval for server-to-server and typically greater than 30 seconds for mobile-to-server; these are directional examples, not mandatory rules.
- The cost of holding a dead connection and the consequences of mistakenly closing a live connection.

Typically, the interval must be shorter than the idle timeout of intermediate infrastructure if the goal is to keep the connection from being dropped due to inactivity. Max lifetime should be longer than the interval by enough to tolerate several delayed or lost heartbeats. Do not pick the two values purely by guesswork; measure in your real deployment environment.

## 4. Configuring Keepalive in Spring Framework

Spring provides **RSocketRequester** to send requests at the object level. Its builder allows configuring **io.rsocket.core.RSocketConnector** directly via the **rsocketConnector** callback.

The example below configures a TCP client to send keepalive every 20 seconds and consider the peer disconnected if no keepalive is received within 90 seconds:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
class RSocketClientConfiguration {

    @Bean
    RSocketRequester rSocketRequester() {
        return RSocketRequester.builder()
                .rsocketConnector(connector ->
                        connector.keepAlive(
                                Duration.ofSeconds(20),
                                Duration.ofSeconds(90)))
                .tcp("localhost", 7000);
    }
}
~~~

Explanation:

- **rsocketConnector(...)** allows customizing the low-level RSocket Java connector.
- **keepAlive(interval, maxLifeTime)** sets the frame emission frequency and the wait time for frames from the peer.
- **tcp("localhost", 7000)** selects the TCP transport. Spring also supports WebSocket connections via the corresponding builder; keepalive configuration still belongs to the RSocket connector.
- Calling **tcp(...)** creates a shared requester. The connection is typically established when the application starts sending requests, not necessarily at bean creation time.

If customization is not needed, you can use RSocket Java's default values. Configure explicitly when you need to align timeouts with network infrastructure or have specific disconnect detection time requirements.

## 5. Observing When a Connection Closes

Configuring heartbeats only helps detect an unresponsive peer. The application still needs to observe the connection lifecycle to log events, update registries, or trigger recovery workflows.

### Observing Inbound Server Connections with @ConnectMapping

On the server side, **@ConnectMapping** handles the **SETUP** frame. From the **RSocketRequester** received in the handler, you can obtain the active RSocket and register a listener via **onClose()**.

~~~java
import io.rsocket.RSocket;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.handler.annotation.ConnectMapping;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Controller;

@Controller
class RSocketConnectionObserver {

    private static final Logger log =
            LoggerFactory.getLogger(RSocketConnectionObserver.class);

    @ConnectMapping
    void onConnect(RSocketRequester requester) {
        RSocket socket = requester.rsocket();

        if (socket == null) {
            log.warn("Could not obtain an active RSocket to observe");
            return;
        }

        socket.onClose()
                .doOnError(error ->
                        log.warn("RSocket connection closed with error", error))
                .doFinally(signal ->
                        log.info("RSocket connection lifecycle ended: {}", signal))
                .subscribe();
    }
}
~~~

**onClose()** returns a **Mono<Void>** that terminates when the RSocket is closed. If it terminates due to an error, the error is emitted via **onError**; if closed normally, the publisher completes. **doFinally** runs when the publisher terminates with complete, error, or cancel.

In a client application that creates a requester using the modern builder, **requester.rsocket()** may return **null** because the requester holds an **RSocketClient** rather than a direct RSocket. When you need to observe that client's lifecycle, use:

~~~java
requester.rsocketClient().onClose()
        .doOnError(error ->
                log.warn("RSocket client connection closed with error", error))
        .doFinally(signal ->
                log.info("RSocket client connection terminated: {}", signal))
        .subscribe();
~~~

Register the listener in an appropriate lifecycle-managing component and ensure the subscription is managed during application shutdown. Do not create a new subscription every time a request is sent.

## 6. Keepalive, Request Timeout, and Resumption Are Not the Same

| Mechanism | Question Answered | Scope |
| --- | --- | --- |
| Keepalive / max lifetime | Is the peer still responding over the RSocket connection? | Entire connection |
| Request timeout | Did this business request return a result on time? | A single request or stream |
| Transport close/error | Has TCP or WebSocket reported a close/error? | Transport connection |
| Session resumption | Can the session/streams continue after the transport was interrupted? | Session and resume state |
| Reconnect | Can a new connection be opened after the old connection is lost? | New connection |

A successful keepalive does not prove a business request will succeed. The peer may still answer control frames while a handler, database, or dependent service is slow. Therefore, requests still need their own timeouts and error handling.

Conversely, a failed request stream does not necessarily mean the entire connection is dead. RSocket has stream-level errors and connection-level errors. **RSocket.onClose()** observes connection-level errors (Stream ID 0); business errors on a single stream must be handled on that request's publisher.

Keepalive also does not automatically resend requests or restore streams. Reconnect creates a new connection according to the configured policy. Resumption is a separate mechanism requiring support from both peers and maintaining the necessary session state. If retrying a request after a disconnect, consider the case where the server finished processing but the response was lost; requests with side effects need an idempotency key or idempotent design to avoid duplicate execution.

## 7. Diagnostic Procedure When a Connection Times Out

When you see keepalive errors or closed connections, check in order:

1. **Identify error scope:** did the error occur only on one stream, or did the connection-level **onClose()** listener also terminate?
2. **Read the close reason:** distinguish transport errors, protocol errors, keepalive timeouts, and active shutdown closures.
3. **Compare timings:** compare interval, max lifetime, request timeout, and idle timeouts of proxies/load balancers/firewalls.
4. **Check process latency:** inspect JVM pauses, CPU saturation, blocked event loops, or starved schedulers.
5. **Check the network:** look for signs of network switching, NAT timeouts, packet loss, resets, or WebSocket connections closed by a proxy.
6. **Inspect frames:** when deep analysis is needed, enable RSocket Java frame logging at DEBUG level (logger **io.rsocket.FrameLogger**) in a controlled test environment.
7. **Evaluate recovery:** decide between reconnect, resumption, or requiring the client to create a new session. Check retry safety for requests with side effects.

Do not increase **maxLifetime** immediately upon encountering a timeout without identifying the root cause. Large values can mask a faulty network path and prolong resource retention. Also avoid aggressively reducing the interval to compensate for a blocked event loop; heartbeats still require a healthy scheduler and transport.

## 8. Common Misconceptions

- **Assuming an active TCP connection means the peer is alive:** TCP can be in a half-open state after a silent network drop.
- **Assuming a request timeout eliminates the need for keepalive:** a request timeout only detects a slow operation; it does not maintain and probe an idle connection.
- **Using max lifetime as a business timeout:** the two timeouts have different scopes and purposes.
- **Setting max lifetime close to interval:** a single delayed or lost heartbeat can cause a false positive. Allow multiple missed cycles.
- **Assuming keepalive automatically reconnects:** keepalive detects peer status; reconnect and resumption must be configured and handled separately.
- **Assuming keepalive proves the entire application is healthy:** it verifies responsiveness at the protocol layer, not databases, queues, or business logic.
- **Retrying every request after a connection closes:** the response may have been lost after the server executed a side effect. Idempotency or reconciliation is required.

## 9. Illustrative Scenario

Suppose a client configures an interval of 20 seconds and a max lifetime of 90 seconds:

- When the connection is stable, the client sends periodic keepalives and the server responds. The connection remains monitored even with no business requests.
- When a router silently drops the path, the client may still think the socket is open. Subsequent keepalive frames receive no response.
- Once max lifetime is exceeded, the client concludes the peer is no longer responsive and the connection is marked terminated according to the implementation's behavior.
- Requests/streams depending on the connection may emit errors. The application records the close event, releases resources, and applies the appropriate reconnect/resume policy.
- If only one request exceeds its timeout while **onClose()** has not terminated, handle that request's error first; do not assume the entire connection is lost.

## 10. Implementation Checklist

- [ ] Interval chosen based on client type and infrastructure idle timeouts.
- [ ] Max lifetime allows multiple missed heartbeats and fits real-world latency.
- [ ] Verified keepalive configuration sent in **SETUP**.
- [ ] Connection close/error observed with **onClose()** on the appropriate side.
- [ ] Business requests still have their own timeouts.
- [ ] Retries are bounded and safe with side effects; resumption is configured separately if needed.
- [ ] Tested both explicit transport closure and silent network loss scenarios.
- [ ] Logs/metrics are sufficient to distinguish stream errors, connection errors, and timeouts.

## References

- [RSocket Protocol — SETUP and KEEPALIVE frames](https://github.com/rsocket/rsocket/blob/master/Protocol.md#frame-setup)
- [RSocket Protocol — KEEPALIVE frame and dead transport handling](https://github.com/rsocket/rsocket/blob/master/Protocol.md#keepalive-frame-0x03)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework API — RSocketRequester](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [RSocket Java API — RSocketConnector.keepAlive](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
