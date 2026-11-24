# Message Size Limits, Send Timeouts, and Buffers in STOMP

## 1. Why Are Resource Limits Needed?

In a Spring application supporting STOMP over WebSocket, messages pass through multiple layers: WebSocket transport, the STOMP processor, internal channels, the message broker, and the connection to each client. Each layer has its own type of limit.

A large message may require multiple WebSocket frames to transmit. A client on a slow connection may consume messages slower than the server emits them. When that happens, outbound pending messages accumulate in the session's buffer. Without limits on size and queued data volume, a slow client can occupy server memory and sending resources for an extended period.

Spring provides three important groups of limits on the server side:

- \`messageSizeLimit\`: limits the size of an inbound STOMP message after reassembling related WebSocket messages.
- \`sendTimeLimit\`: limits the time spent sending to a WebSocket session.
- \`sendBufferSizeLimit\`: limits the number of bytes held in a WebSocket session's send buffer.

On the STOMP client side, \`WebSocketStompClient\` has its own inbound limit and an option to split outbound messages. This is separate from the server's send limits.

## 2. Distinguishing Types of Message Sizes

Three concepts must be distinguished:

| Concept | Meaning | Where Configured |
| --- | --- | --- |
| WebSocket frame/message | Unit of data sent and received by the WebSocket transport | WebSocket server/container and WebSocket client |
| STOMP message/frame | Protocol unit consisting of command, headers, and body; may span multiple WebSocket messages | Spring STOMP transport or STOMP client |
| Business payload | Application content after MessageConverter decodes it, e.g., a JSON DTO | API contract, converter, and application logic |

Spring STOMP limits are not synonymous with the limit of an individual WebSocket frame. A STOMP message may be split into multiple WebSocket messages and reassembled before Spring processes it. Conversely, the WebSocket container still enforces its own limit on each transport message/frame.

Therefore, when encountering a "message too large" error, you must identify which limit was exceeded: the WebSocket container limit, the server STOMP limit, the STOMP client inbound limit, or the limit of an intermediary layer such as a reverse proxy or broker.

## 3. Inbound Message Limits on the Server Side

### 3.1. WebSocketTransportRegistration.setMessageSizeLimit

The \`setMessageSizeLimit(int)\` method configures the maximum size of an inbound sub-protocol message, such as a STOMP frame that may be reassembled from multiple WebSocket messages.

The Spring Framework default is **64 KB (64 × 1024 bytes)**. When a STOMP message exceeds this limit, message processing is rejected and a protocol conversion error may occur.

Example configuring a 128 KB limit:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {

        registration.setMessageSizeLimit(128 * 1024);
    }
}
\`\`\`

Here:

- \`128 * 1024\` is 131,072 bytes, equivalent to 128 KiB.
- The limit applies to one inbound STOMP sub-protocol message after Spring reassembles the required parts.
- This configuration does not replace the WebSocket message size limit of Tomcat, Jetty, Undertow, or the container running the application.

### 3.2. Why Can a STOMP Message Be Split?

A WebSocket server may enforce a limit per WebSocket message. For example, Spring documentation notes common defaults of around 8 KB on Tomcat and 64 KB on Jetty. To transmit a larger STOMP message, a STOMP client can split the data into multiple WebSocket messages.

Some JavaScript STOMP clients, such as \`@stomp/stompjs\`, split large messages into chunks of around 16 KB. Spring STOMP-over-WebSocket can reassemble these parts and lets you configure the limit at the STOMP message level. Spring also adjusts WebSocket message sizes when necessary so that WebSocket chunks of at least 16 KB can be carried in a transport-supported manner.

Do not assume every client, server, and proxy fragments messages the same way. Check the documentation for the WebSocket container and client in use, then test with realistic large messages.

## 4. Outbound Send Time and Buffer on the Server Side

### 4.1. Why Are These Two Limits Needed?

WebSocket servers typically require messages sent to the same session to be written sequentially from one thread at a time. Spring's \`@EnableWebSocketMessageBroker\` configuration ensures sends to a session are coordinated according to that requirement.

If a client receives messages slower than the server emits them, subsequent messages must wait in the buffer. This situation can happen when:

- The client is on a weak mobile network or low-bandwidth connection.
- The client pauses reading because a browser tab is frozen or the device is overloaded.
- The server broadcasts many messages or messages with large payloads.
- The client processes messages slowly and socket sends stall.

\`sendTimeLimit\` limits the send duration, while \`sendBufferSizeLimit\` limits the amount of pending outbound data. The two values work together to prevent a slow session from holding buffers indefinitely.

### 4.2. sendTimeLimit

\`WebSocketTransportRegistration.setSendTimeLimit(int)\` takes a duration in milliseconds. The Spring Framework default is **10 seconds (10,000 ms)**.

When sending to a slow session, subsequent messages are buffered. If either the time limit or the buffer size limit is hit, Spring clears the session's pending send state and attempts to close that session.

There is an important detail: Spring only checks the time limit when an additional send occurs. If only one message is currently sending and that operation hangs, this limit may not close the session immediately; the check may have to wait until another message is sent or a physical socket timeout occurs. Thus, \`sendTimeLimit\` does not replace WebSocket server, HTTP connection, or operating system timeouts.

The value must be greater than 0; non-positive values are ignored. Choose the limit based on acceptable latency and message emission rate, rather than increasing the timeout just to hide slow clients.

### 4.3. sendBufferSizeLimit

\`WebSocketTransportRegistration.setSendBufferSizeLimit(int)\` sets the maximum number of bytes buffered when sending to a WebSocket session. With SockJS fallback, the limit also applies to data waiting to be written to the HTTP response.

The Spring Framework default is **512 KB (512 × 1024 bytes)** per session.

If the value is less than or equal to 0, buffering is effectively disabled. When messages are sent slower than the emission rate, the buffer can fill up before the client consumes the data. When either send limit is exceeded, Spring clears the session state and attempts to close the connection.

Closing the session at the framework layer does not guarantee the physical socket always closes immediately. With blocking I/O, the close operation can hang or fail to complete as expected. Prefer configuring non-blocking I/O connectors on the WebSocket server if possible.

### 4.4. Configuring Both Limits Together

Example configuring a 15-second send timeout and a 512 KiB buffer:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketPerformanceConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {

        registration
                .setSendTimeLimit(15 * 1000)
                .setSendBufferSizeLimit(512 * 1024);
    }
}
\`\`\`

All three limits can be combined in one configuration:

\`\`\`java
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {

    registration
            .setMessageSizeLimit(128 * 1024)
            .setSendTimeLimit(15 * 1000)
            .setSendBufferSizeLimit(512 * 1024);
}
\`\`\`

There is no single set of values right for every application. 128 KiB, 15 seconds, and 512 KiB are only examples to illustrate the API. Tune them according to payload size, broadcast frequency, concurrent connection count, bandwidth, and the latency your product tolerates.

## 5. Configuration on the WebSocketStompClient Side

Properties on \`WebSocketStompClient\` control how the Java client handles its own messages. They do not replace the server configurations in the previous sections.

### 5.1. Inbound message size limit

\`setInboundMessageSizeLimit(int)\` sets the maximum size of an inbound STOMP message on the client side. Because a STOMP message can arrive across multiple WebSocket messages, the client needs a buffer to reassemble the parts. The default is **64 KiB**.

If an inbound message exceeds the limit, the client throws \`StompConversionException\`.

### 5.2. Outbound message size limit

Since Spring Framework 6.2, \`setOutboundMessageSizeLimit(Integer)\` allows setting a limit for the client's outbound STOMP messages. If a message is larger than the limit, the client splits the STOMP message into multiple WebSocket messages for the receiver to reassemble.

By default this property is unset, so the client does not automatically split outbound messages according to this limit. Splitting requires the receiver to be capable of reassembling message parts.

Example:

\`\`\`java
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

WebSocketStompClient stompClient =
        new WebSocketStompClient(new StandardWebSocketClient());

stompClient.setInboundMessageSizeLimit(128 * 1024);
stompClient.setOutboundMessageSizeLimit(128 * 1024);
\`\`\`

The configuration above adjusts only the Java client. The server must still allow receiving the corresponding message via \`setMessageSizeLimit\` and appropriate WebSocket container limits. Conversely, increasing the server limit does not automatically increase the client's inbound limit.

### 5.3. Configuration Comparison Table

| Property | Applied Side | Message Direction | Spring Framework Default |
| --- | --- | --- | --- |
| \`WebSocketTransportRegistration.setMessageSizeLimit\` | Server | Inbound STOMP message | 64 KiB |
| \`WebSocketTransportRegistration.setSendTimeLimit\` | Server | Outbound send to each session | 10 seconds |
| \`WebSocketTransportRegistration.setSendBufferSizeLimit\` | Server | Outbound buffer of each session | 512 KiB |
| \`WebSocketStompClient.setInboundMessageSizeLimit\` | Java client | Inbound STOMP message | 64 KiB |
| \`WebSocketStompClient.setOutboundMessageSizeLimit\` | Java client | Outbound STOMP message | Unset; no splitting by this property |

Do not add or substitute these limits for one another. They belong to different layers and transmission directions.

## 6. Estimating Memory When There Are Many Slow Clients

Buffer limits are scoped per WebSocket session. As the number of clients increases, total potential memory devoted to pending outbound messages increases accordingly.

Rough estimate:

\`\`\`text
Total maximum buffer
    ≈ number of slow sessions × sendBufferSizeLimit per session
\`\`\`

Example with 5,000 sessions and a 512 KiB/session limit:

\`\`\`text
5,000 × 512 × 1,024
= 2,621,440,000 bytes
≈ 2.44 GiB
\`\`\`

This is an upper-bound calculation assuming all sessions hit the limit simultaneously. It does not include object overhead, queue metadata, payload copies, broker memory, and other memory regions. Not every session uses its full buffer, but the calculation shows that a "small" per-connection limit can become a large consumption at the scale of thousands of connections.

When designing, define a memory budget for outbound buffering, maximum sessions, slow-client ratio, and p95/p99 message size. If many sessions frequently hit the limit, address the root cause in publish rate, payload size, or client consumption capacity.

## 7. Application-Layer Backpressure

Transport limits protect memory and session lifecycles. They do not automatically give the application complete business-level backpressure. If the system continuously emits more messages than clients can handle, closing sessions is only a last-resort safeguard.

Ways to reduce load:

- **Reduce payload size:** send only necessary fields, use small DTOs, and avoid sending entire entities or large object graphs.
- **Paginate or load on demand:** large historical datasets should be fetched via paginated REST/API calls or a bounded loading mechanism, then use STOMP for change events.
- **Coalesce updates:** if clients only need the latest state, combine multiple consecutive changes into one snapshot or aggregate event.
- **Rate-limit emission:** throttle or debounce high-frequency events when business rules allow.
- **Drop stale data:** for real-time current-value data, stale updates can be discarded before sending.
- **Isolate critical flows:** prevent important events from being blocked by telemetry streams or lower-priority jobs; use separate destinations/queues and appropriate handling policies.
- **Scope subscriptions:** clients subscribe only to the destinations and data scope the current screen actually needs.
- **Move large payloads to storage:** send an ID or time-limited URL for clients to download large files over HTTP instead of broadcasting full binaries over STOMP.

Only drop messages when the business contract permits. For financial events, orders, or control commands, dropping messages can corrupt state; use sequences, replay, or business acknowledgments instead of arbitrary coalescing.

## 8. Tuning Thread Pools and Channels

Messages in Spring STOMP are processed asynchronously through channels with thread pools, specifically:

- \`clientInboundChannel\`: processes messages coming from clients into the application.
- \`clientOutboundChannel\`: sends messages from the application/broker to clients.

According to Spring documentation, the thread pools of these two channels are typically configured by default at twice the number of available processors. Tune based on the type of work:

- If inbound handlers are primarily CPU-bound, a thread count close to the processor count is usually a reasonable starting point.
- If inbound handlers frequently wait on a database or external service, more threads may be needed to reduce wait time.
- If outbound has many clients on slow networks, send threads can be occupied longer and the outbound queue grows.

A common misconception in \`ThreadPoolExecutor\`: increasing max pool size does not mean the thread pool will automatically grow to that size. If the queue has a very large default capacity, new tasks are usually queued after the core pool is busy, so the pool may never scale beyond core size. Understand core size, max size, and queue capacity together before tuning.

Example tuning channels:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompChannelConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureClientInboundChannel(
            ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(16)
                .queueCapacity(500);
    }

    @Override
    public void configureClientOutboundChannel(
            ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(16)
                .queueCapacity(500);
    }
}
\`\`\`

These are illustrative values, not recommended settings for every load. When changing queue capacity, decide how the application handles overload/rejection and ensure you do not lose messages that business logic requires to be delivered. Tuning thread pools does not replace \`sendTimeLimit\` or \`sendBufferSizeLimit\`.

## 9. Observation and Diagnostics

Spring provides \`WebSocketMessageBrokerStats\` to monitor STOMP/WebSocket activity. Useful metrics include:

- Number of open WebSocket sessions and closed sessions.
- Counts of CONNECT, CONNECTED, DISCONNECT frames.
- Size and state of the \`clientInboundChannel\` thread pool.
- Size and state of the \`clientOutboundChannel\` thread pool.
- SockJS scheduler statistics when used.

How to interpret:

| Symptom | Possibility to Check |
| --- | --- |
| Inbound queue grows continuously | Slow application handlers, blocking DB/HTTP queries, or insufficient inbound pool |
| Outbound queue grows | Slow-consuming clients, weak networks, or server broadcasting too fast |
| Sudden spike in closed sessions | Possibly hitting send timeout/buffer limits, heartbeat timeouts, or transport errors |
| STOMP messages rejected | Message exceeded \`messageSizeLimit\` or protocol/converter errors |
| Many sessions increasing buffer simultaneously | Payload too large, high emission frequency, or many clients falling behind |
| High CPU but low queue | CPU-bound processing or expensive payload serialization/deserialization |

Combine stats with broker, WebSocket container, JVM heap, GC, network throughput, and application metrics. Looking only at the number of open connections is not enough to assess system health.

Do not log full payloads or sensitive headers. When tracing is needed, use correlation IDs, properly sanitized session IDs, and message size statistics.

## 10. Testing Limits and Slow Clients

A performance test should verify both normal behavior and protective behavior when limits are exceeded.

1. **Messages below the limit:** send a normal STOMP message and verify the server/client receives the exact payload.
2. **Messages near the limit:** test sizes just below and right at the configured threshold.
3. **Messages exceeding the limit:** verify the message is rejected at the appropriate layer and the error is clearly observable.
4. **WebSocket fragmentation:** send a large STOMP message split into multiple WebSocket messages and verify Spring reassembles it successfully.
5. **Slow-reading client:** create a client that intentionally reads data slower than the server emits; observe buffer, send time, and session closure when limits are hit.
6. **Burst traffic:** send many consecutive messages to verify whether buffers grow unboundedly.
7. **Multiple clients:** run multiple sessions at varying bandwidths to evaluate the impact of a slow client group on other sessions.
8. **After closure:** verify the client can reconnect per application policy, re-create subscriptions, and resynchronize data.
9. **Compare configurations:** run the same workload with different thresholds; compare throughput, p95/p99 latency, heap, closed session count, and queue depth.

Do not test only the happy path with one client on localhost. The most important scenario to verify for \`sendTimeLimit\` and \`sendBufferSizeLimit\` is when a client is slow or stops reading messages while the server continues sending.

## 11. Common Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Large STOMP message fails even after raising WebSocket container limit | Spring's \`messageSizeLimit\` is still low | Increase \`setMessageSizeLimit\` appropriately and also check client limits |
| Message truncated or fails to reassemble | Client/server does not support fragmentation as expected or transport limits are incompatible | Check STOMP client framing behavior and WebSocket container configuration |
| Java client gets conversion error on large messages | Client-side \`inboundMessageSizeLimit\` is low | Increase \`setInboundMessageSizeLimit\` after determining valid size |
| Outbound client sends one very large message | \`outboundMessageSizeLimit\` unset or receiver does not support frame reassembly | Configure client limit and verify receiver |
| Slow client gets disconnected | Buffer or send time exceeded threshold | Review throughput, payload, frequency, and session policy |
| Heap grows with many slow clients | Total per-session buffer too large | Lower buffer, reduce fan-out, coalesce events, and cap session counts |
| Increasing max pool size does not raise throughput | Large queue causes tasks to be queued instead of creating more threads | Evaluate core/max pool and queue capacity together |
| Increasing sendTimeLimit still leaves sockets hanging | Limit is checked on the next send, does not replace socket timeouts | Configure container/transport timeouts and use non-blocking I/O |

## 12. Process for Choosing Limits

You can use the following process to tune:

1. Measure actual STOMP message sizes, including p50/p95/p99 distribution and maximum valid size.
2. Choose \`messageSizeLimit\` large enough for the largest valid message with a reasonable headroom, while keeping a cap against abnormal payloads.
3. Check per-WebSocket-message limits of the container, proxy, and client to ensure STOMP parts are transmitted and reassembled properly.
4. Measure server send rate and client consumption rate; determine how long a slow client may hold a backlog.
5. Choose \`sendBufferSizeLimit\` based on the heap budget per session and total concurrent sessions.
6. Choose \`sendTimeLimit\` based on acceptable wait before considering a session unable to keep up.
7. Use load testing to verify behavior when thresholds are reached and monitor closed sessions.
8. If you have to keep raising limits to avoid disconnects, revisit payload design, emission frequency, and backpressure mechanisms.

The goal is to allow valid messages through, cap resources held by slow clients, and keep latency within a range the system can tolerate.

## Official References

- [Spring Framework — Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html): thread pools, send time, send buffer, and inbound STOMP size limits.
- [WebSocketTransportRegistration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketTransportRegistration.html): contract, units, and default values of \`setMessageSizeLimit\`, \`setSendTimeLimit\`, \`setSendBufferSizeLimit\`.
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html): inbound/outbound limits of \`WebSocketStompClient\`, message fragmentation, and receipts.
- [WebSocketStompClient Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html): \`setInboundMessageSizeLimit\` and \`setOutboundMessageSizeLimit\` APIs.
- [Spring Framework — Monitoring](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html): session, STOMP frame, and channel executor statistics.

**Key takeaway:** \`messageSizeLimit\` protects inbound STOMP message sizes; \`sendTimeLimit\` and \`sendBufferSizeLimit\` protect sending to each slow WebSocket session. Java client limits and WebSocket container limits are independent layers, so they must be configured and tested consistently across all relevant layers.
