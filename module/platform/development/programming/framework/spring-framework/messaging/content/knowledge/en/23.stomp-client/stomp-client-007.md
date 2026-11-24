# TaskScheduler, Heartbeats, and Message Size Limits

When using Spring's `WebSocketStompClient`, `TaskScheduler` handles the STOMP client's periodic tasks, notably sending heartbeats and tracking RECEIPT timeouts. At the same time, the client enforces a buffer limit for incoming STOMP messages to reassemble a message that may be split across multiple WebSocket messages. These limits must be understood per transmission direction, because client configuration, WebSocket server configuration, and container limits are separate layers.

This lesson focuses on Spring Framework 6.1's Java STOMP client. APIs added in Spring 6.2 are noted separately where differences exist.

## 1. Role of TaskScheduler in the STOMP client

`WebSocketStompClient` is an adapter layering the STOMP protocol onto a `WebSocketClient`. It manages connecting, encoding and decoding STOMP frames, converting payloads, and creating `StompSession` instances for the application to send, subscribe, or process messages.

A STOMP client typically performs the following tasks:

- Opening a WebSocket connection to the server's endpoint.
- Sending a `CONNECT` frame and receiving a `CONNECTED` frame.
- Sending `SUBSCRIBE`, `SEND`, `UNSUBSCRIBE`, and other STOMP frames.
- Receiving `MESSAGE`, `ERROR`, `RECEIPT` and processing payloads.
- Maintaining heartbeats when the connection has no traffic.
- Tracking requested receipts to know whether frames have been processed by the server.

`TaskScheduler` provides a scheduler for time-based tasks. In `WebSocketStompClient`, the scheduler is used for heartbeats and receipt tracking. It is not a thread pool for running payload logic in callbacks, does not replace `TaskExecutor`, and is not the server-side simple broker's scheduler.

This distinction matters when an application both runs a STOMP client to connect to another system and exposes a STOMP server to serve external clients. The scheduler passed to `WebSocketStompClient` belongs to the client side; the scheduler configured in `MessageBrokerRegistry` belongs to the server-side broker. Both components have separate lifecycles and responsibilities.

## 2. Declaring TaskScheduler for WebSocketStompClient

You can use `ThreadPoolTaskScheduler` as a Spring bean. This bean has its lifecycle managed by the container and is injected into `WebSocketStompClient`:

~~~java
package com.example.messaging.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.converter.StringMessageConverter;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

@Configuration
public class StompClientConfiguration {

    @Bean
    public ThreadPoolTaskScheduler stompClientTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("stomp-client-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }

    @Bean
    public WebSocketStompClient webSocketStompClient(
            TaskScheduler stompClientTaskScheduler) {

        WebSocketStompClient client =
                new WebSocketStompClient(new StandardWebSocketClient());

        client.setMessageConverter(new StringMessageConverter());
        client.setTaskScheduler(stompClientTaskScheduler);
        client.setDefaultHeartbeat(new long[] {10_000, 10_000});
        client.setReceiptTimeLimit(15_000);
        client.setInboundMessageSizeLimit(128 * 1024);

        return client;
    }
}
~~~

The example sets pool size to 2 for illustration; the right thread count depends on session count, task frequency, and actual load. If the application has multiple beans of type `TaskScheduler`, use `@Qualifier("stompClientTaskScheduler")` on the injection parameter to select the right bean.

Key points to note:

- `setTaskScheduler(...)` enables the scheduler for heartbeats and receipt tracking.
- `setDefaultHeartbeat(...)` sets the two default heartbeat values sent by the client in the `CONNECT` frame.
- `setReceiptTimeLimit(...)` sets the maximum time to wait for a receipt before considering it expired. The default is 15,000 ms.
- `setInboundMessageSizeLimit(...)` sets the maximum buffer size for an incoming STOMP message. The example uses 128 KiB.
- `setMessageConverter(...)` chooses how payloads are converted. The example uses `StringMessageConverter` for text payloads; if sending DTO/JSON, an appropriate JSON converter is required.

Do not create a new scheduler per message. For a client with multiple sessions, the scheduler is shared to run periodic tasks for that client.

### Special default of WebSocketStompClient

The base class `StompClientSupport` has a default heartbeat of `10000,10000`, whereas `WebSocketStompClient`'s constructor sets the default to `0,0`. When calling `setTaskScheduler(...)`, if the heartbeat is still `0,0`, the client automatically switches back to the recommended `10000,10000`.

Therefore, if you want to customize heartbeats, configure the scheduler first and then call `setDefaultHeartbeat(...)` with the desired values. This avoids confusion between the base class default and `WebSocketStompClient`'s own default.

Some transports have their own heartbeat support and do not need a scheduler solely to send/receive heartbeats. However, if the application needs RECEIPT tracking, `TaskScheduler` still needs to be configured.

## 3. Client-side heartbeats

A heartbeat is a periodic STOMP signal allowing both sides to detect an inactive connection. It is exchanged when no regular STOMP messages have been sent within the corresponding interval. If the client just sent `SEND` or the server just sent `MESSAGE`, that data also counts as activity on the connection; an empty heartbeat does not need to be emitted right then.

In STOMP, the `heart-beat` header contains two numbers in milliseconds. In the client's `CONNECT` frame:

- The first number indicates the interval at which the client can send heartbeats.
- The second number indicates the interval at which the client wants to receive heartbeats from the server.
- A value of `0` means the client does not support sending or does not request receiving heartbeats in that direction.

A Spring client sets these two values via:

~~~java
client.setDefaultHeartbeat(new long[] {10_000, 15_000});
~~~

In the example above, the client can send a heartbeat at most as frequently as every 10 seconds and expects the server to send heartbeats around every 15 seconds, before negotiating with the server's capabilities.

### Bidirectional negotiation

The server returns a `heart-beat` pair in the `CONNECTED` frame. Let:

- Client declare `cx, cy`.
- Server declare `sx, sy`.

The heartbeat interval is negotiated independently for each direction:

~~~text
Client -> Server:
  No heartbeat if cx = 0 or sy = 0
  If both are non-zero: interval = max(cx, sy)

Server -> Client:
  No heartbeat if sx = 0 or cy = 0
  If both are non-zero: interval = max(sx, cy)
~~~

For example, if the client declares `10000,15000` and the server returns `5000,20000`:

- Client → server: `max(10000, 20000) = 20000` ms, or 20 seconds.
- Server → client: `max(5000, 15000) = 15000` ms, or 15 seconds.

Values in `setDefaultHeartbeat(...)` are only client-side proposals. The actual intervals depend on both sides. If the client sends no heartbeat header or either side sets the required value to 0, that direction will have no negotiated heartbeat.

### Inactivity tracking and disconnect detection

Once a scheduler is configured, the client can:

1. Track when data was last sent to decide when a heartbeat needs to be sent.
2. Track when data was last received from the server.
3. Detect when the server sends no data within the negotiated interval.
4. Forward connection errors to `StompSessionHandler` via the transport error callback.

Heartbeats only detect connection liveness according to protocol rules. They do not confirm a message was saved to a database or finished business processing. If you need to know the server processed a `SEND` or `SUBSCRIBE` frame, use RECEIPT.

## 4. TaskScheduler and STOMP RECEIPT

STOMP RECEIPT is a mechanism confirming the server processed a frame that the client sent with a `receipt` header. It differs from heartbeats:

- Heartbeats check connection liveness.
- RECEIPT confirms processing of a specific frame.
- ACK/NACK relates to confirming message consumption on the client side, depending on subscription acknowledgment mode.

In Spring, `TaskScheduler` also monitors the RECEIPT wait deadline. `StompClientSupport` defaults the receipt time limit to 15 seconds; this can be changed with `setReceiptTimeLimit(...)`.

With `StompSession`, you can enable automatically adding receipts for send and subscribe operations:

~~~java
session.setAutoReceipt(true);
~~~

`send` and `subscribe` return a `Receiptable`, allowing callbacks to be registered when the receipt arrives or when the operation expires. Example:

~~~java
Receiptable receipt = session.send("/app/orders", orderPayload);

receipt.addReceiptTask(() ->
        System.out.println("Server confirmed the frame"));
receipt.addReceiptLostTask(() ->
        System.out.println("RECEIPT was not received within the time limit"));
~~~

For expiration tasks to be tracked, the client needs a `TaskScheduler`. Without a configured scheduler, do not enable auto-receipt and expect the client to track confirmation deadlines automatically.

A receipt only proves the server processed the frame according to STOMP rules. It does not automatically prove business logic committed a transaction or data was durably persisted. If the application requires business confirmation, return a separate business result after processing finishes.

## 5. Inbound STOMP message size limit on the client

`WebSocketStompClient` has an `inboundMessageSizeLimit` property, configured via:

~~~java
client.setInboundMessageSizeLimit(128 * 1024);
~~~

The value is in bytes. The default is `64 * 1024` bytes, or 64 KiB. This is the buffer limit for an incoming STOMP message entering the client.

A STOMP message can be transported across multiple WebSocket messages. When that happens, the client must reassemble the parts to decode the entire STOMP frame. `inboundMessageSizeLimit` limits the total size allowed to be buffered for one reassembled message; it is not merely the limit of a single WebSocket frame.

If an incoming STOMP message exceeds the limit, decoding/conversion fails, usually reported as `StompConversionException`. Raising the limit permits receiving larger messages, but also increases the memory potentially required for each message being buffered.

Example:

~~~java
WebSocketStompClient client =
        new WebSocketStompClient(new StandardWebSocketClient());

client.setInboundMessageSizeLimit(256 * 1024);
~~~

This configuration allows buffering an incoming STOMP message up to 256 KiB on the client side. The value should be based on the largest valid message size the application genuinely needs, plus an appropriate margin for headers and payload.

### Which direction does this limit apply to?

`WebSocketStompClient.setInboundMessageSizeLimit(...)` applies to messages traveling from the server to this STOMP client. It does not limit messages that the client sends up to the server.

If the client sends a large message to the server, the server's inbound limit and the server-side WebSocket container's limit are the places to check. You cannot raise the client's inbound limit to fix an error where the server rejects messages sent by the client.

## 6. Size limits on the server and WebSocket container

On the server side, Spring provides `WebSocketTransportRegistration.setMessageSizeLimit(...)` inside `configureWebSocketTransport(...)` to limit the size of an inbound sub-protocol message, such as a STOMP frame assembled from multiple WebSocket messages.

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketServerConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {
        registration.setMessageSizeLimit(128 * 1024);
    }
}
~~~

The default server-side STOMP message limit is 64 KiB. Configuring `128 * 1024` allows the server to buffer a STOMP message up to 128 KiB before processing.

Three layers must be distinguished:

| Limit layer | API / configuration location | Applicable direction |
|---|---|---|
| Client STOMP message buffer | `WebSocketStompClient.setInboundMessageSizeLimit(...)` | Server → client |
| Spring server STOMP message buffer | `configureWebSocketTransport(...).setMessageSizeLimit(...)` | Client → server |
| Single WebSocket message/frame size in transport container | WebSocket client/server container configuration | Depends on direction and transport |

A STOMP message can be split into multiple WebSocket messages. Spring supports reassembling those parts; Spring's performance documentation notes that common STOMP clients may split large messages on 16 KiB boundaries. Therefore, the limit of a single WebSocket message in the container must be compatible with how the client fragments messages. Spring adjusts WebSocket message limits to support at least 16 KiB parts in STOMP-over-WebSocket configurations.

Container limits still need separate attention. For example, Spring documentation mentions Tomcat may default to a smaller limit than Jetty; actual values depend on container version and configuration. When encountering frame-too-large errors, check both container configuration and Spring's STOMP message limits.

## 7. Distinguishing message size from send buffer and send time

The Spring server has two additional settings for scenarios involving slow-reading clients:

- `setSendBufferSizeLimit(...)`: limits the amount of data buffered when sending to a WebSocket session.
- `setSendTimeLimit(...)`: limits the time allowed for a single send to a session.

These are limits for the server's outbound flow. When a client reads slower than the server sends, subsequent messages may have to wait in the buffer. When the time limit or buffer size limit is exceeded, Spring clears session state and attempts to close the connection.

Example:

~~~java
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {
    registration
            .setSendTimeLimit(15_000)
            .setSendBufferSizeLimit(512 * 1024)
            .setMessageSizeLimit(128 * 1024);
}
~~~

The three values serve different purposes:

- `sendTimeLimit`: maximum 15 seconds for sending.
- `sendBufferSizeLimit`: maximum 512 KiB of data queued to be sent to one session.
- `messageSizeLimit`: maximum 128 KiB for one inbound STOMP message on the server.

Do not use `sendBufferSizeLimit` in place of `messageSizeLimit`. Small messages can accumulate into a large outbound buffer if the client reads slowly; conversely, a single large inbound message can exceed `messageSizeLimit` even when the outbound buffer is empty.

## 8. Outbound limits of WebSocketStompClient in Spring 6.1

In Spring Framework 6.1, `WebSocketStompClient` has `setInboundMessageSizeLimit(...)` but does not yet have a `setOutboundMessageSizeLimit(...)` API. Therefore, do not write configuration using this outbound method if the project uses Spring 6.1.

For messages sent by the client in Spring 6.1:

- Check the message size limits of the WebSocket client and transport container in use.
- Check the receiving server's inbound STOMP message limit.
- If a business payload is very large, consider splitting data at the application layer, using separate upload/download endpoints, or passing a reference to the data instead of sending the entire content in one STOMP message.
- Check limits of proxies, gateways, and external brokers if present.

Starting in Spring Framework 6.2, `WebSocketStompClient` adds `setOutboundMessageSizeLimit(...)`. When a STOMP message exceeds the configured limit, the client splits it into multiple parts/frames for the receiving side to reassemble. This is a new API in 6.2, not an API available in 6.1.

## 9. Choosing appropriate limit values

Do not raise all limits to a huge number merely to avoid errors. Each connection may have multiple messages buffered; concurrent client counts make total memory grow quickly.

When choosing limits:

1. Measure the actual size of the largest payload in valid use cases.
2. Add STOMP headers and necessary conversion overhead.
3. Set client and server limits matching the direction of data flow.
4. Check WebSocket container, proxy, and broker limits along the entire path.
5. Estimate memory retained when many clients receive large messages simultaneously.
6. Check the impact of slow clients and outbound message consumption rates.
7. Reject invalid payloads with validation or business limits at the application layer.

For JSON payloads, character string length is not always equal to bytes transmitted over the network. UTF-8 can use multiple bytes per character; in addition, STOMP headers and framing occupy space. Measure actual encoded byte sizes rather than merely counting Java characters.

## 10. Common errors and troubleshooting

| Symptom | Common cause | How to check or fix |
|---|---|---|
| Client receives large message and throws StompConversionException | Exceeds inboundMessageSizeLimit | Check incoming STOMP message size and raise the limit in a controlled way. |
| Client sends large message but server rejects it | Server-side STOMP inbound limit or WebSocket container limit too small | Check server-side setMessageSizeLimit and container limits. |
| Configuring setOutboundMessageSizeLimit does not compile | Project uses Spring Framework 6.1 | This API exists from 6.2; in 6.1 control sizes at the application and transport layers. |
| Heartbeats do not run despite setting intervals | WebSocketStompClient lacks a scheduler and default heartbeat is 0,0 | Call setTaskScheduler(...), then set setDefaultHeartbeat(...) if needed. |
| Client detects server disconnect too early | Short heartbeat interval, network jitter, or congested scheduler | Compare heart-beat in CONNECT/CONNECTED and inspect scheduler health. |
| RECEIPT callback never runs | Frame did not request receipt, server did not send receipt, or client lacks scheduler to track timeout | Check receipt header, callbacks, and TaskScheduler. |
| Slow client causes memory growth | Many messages queued for reading or buffer exceeds consumption capacity | Check outbound rate, session count, and server-side sendBufferSizeLimit. |
| Raising limits causes high application memory usage | Too many large messages buffered concurrently | Set limits close to actual need, monitor load, and split payloads at application layer. |
| Client only heartbeats in one direction | Send/receive capabilities do not overlap during negotiation | Compute each direction independently using max and check both value pairs. |
| Shared scheduler causes premature receipt timeouts | Receipt time limit does not fit system latency | Adjust setReceiptTimeLimit(...) based on actual response times. |

## 11. Testing checklist

When configuring `WebSocketStompClient`, test against a controllable STOMP server:

1. Initialize the client with a scheduler and verify the `CONNECT` frame carries the expected heartbeat header.
2. Inspect the `CONNECTED` frame and compute actual heartbeat intervals for both directions.
3. Leave the connection idle to observe heartbeats; then send messages regularly to confirm data activity also counts.
4. Interrupt or delay server responses in a test environment to verify the transport error callback is invoked.
5. Enable auto-receipt, send a frame requesting a receipt, and verify the success callback runs.
6. Create a no-receipt scenario to verify timeout according to `setReceiptTimeLimit(...)`.
7. Send a STOMP message smaller than the limit and verify the client decodes it successfully.
8. Send a message larger than `inboundMessageSizeLimit` and verify the error is detected.
9. Send a message across multiple WebSocket messages to verify the client reassembles all data.
10. Test server inbound limits and WebSocket container limits separately from the client inbound limit.
11. Simulate a slow-reading client to observe server outbound buffer and send time limits.
12. Test concurrent session counts to evaluate the impact of heartbeat tasks and message buffers.

Do not treat a passing heartbeat test as proof that size limits are configured properly. These are two independent mechanisms; test heartbeats, receipts, inbound message buffers, and outbound backpressure separately.

## References

- [Spring Framework 6.1 — STOMP Client](https://docs.spring.io/spring-framework/reference/6.1/web/websocket/stomp/client.html): creating WebSocketStompClient, configuring TaskScheduler, heartbeats, and RECEIPT.
- [Spring Framework 6.1 — Performance](https://docs.spring.io/spring-framework/reference/6.1/web/websocket/stomp/configuration-performance.html): configuring STOMP message limits, send buffer, send time, and how Spring reassembles WebSocket messages.
- [Spring Framework 6.1.8 Javadoc — WebSocketStompClient](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html): setTaskScheduler, setInboundMessageSizeLimit, and the 64 KiB default.
- [Spring Framework 6.1.8 Javadoc — StompClientSupport](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/messaging/simp/stomp/StompClientSupport.html): setDefaultHeartbeat, setReceiptTimeLimit, and the scheduler's role.
- [Spring Framework 6.1.8 Javadoc — WebSocketTransportRegistration](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketTransportRegistration.html): inbound STOMP message limit and buffer/time limits when sending to clients.
- [Spring Framework 6.2 Javadoc — WebSocketStompClient](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html): setOutboundMessageSizeLimit API added in 6.2.
- [STOMP 1.2 Specification — Heart-beating](https://stomp.github.io/stomp-specification-1.2.html#Heart-beating): heartbeat header format and bidirectional negotiation rules.
