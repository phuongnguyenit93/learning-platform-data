# SockJsClient When Fallback Transport Is Needed in Spring STOMP

## Learning Objectives

After this lesson, you can:

- Explain the networking problems SockJS solves and distinguish SockJS from plain WebSocket.
- Configure a SockJS endpoint on the Spring server side.
- Create a SockJsClient with WebSocket and HTTP fallback transports.
- Combine SockJsClient with WebSocketStompClient to use STOMP without changing the application's message-handling model.
- Distinguish WebSocket, XHR streaming, and XHR long polling in terms of data transfer and connection overhead.
- Identify limitations of the Java SockJS client, API differences across Spring versions, and requirements for security, proxies, and resources.
- Design appropriate reconnection, testing, and monitoring when transports are disrupted.

## 1. Why is SockJS needed?

WebSocket creates a long-lived bidirectional connection between client and server. After the HTTP Upgrade succeeds, both sides can send data over the same connection. This approach is effective for realtime applications, but some network environments do not allow WebSocket to operate reliably.

Common scenarios:

- Proxies or firewalls do not forward the HTTP Upgrade header.
- Network infrastructure only permits certain types of HTTP requests.
- Proxies close long-lived connections when they assume the connection is idle.
- Older or restricted client environments lack a suitable WebSocket implementation.
- Two servers need to communicate over a public network with intermediate proxies.

SockJS provides a WebSocket emulation mechanism using multiple transports. The client prefers WebSocket when possible; if that transport cannot be used, the client can try a compatible HTTP method. As a result, the application keeps using a bidirectional messaging model at the application layer.

SockJS does not replace STOMP. The two protocols address two different layers:

- **SockJS** provides data transport and fallback when WebSocket is unavailable.
- **STOMP** defines frames, commands, destinations, subscriptions, and messages at the application layer.

When using STOMP over SockJS, STOMP frames are still sent and received as before; SockJS determines how bytes/messages travel across the network.

## 2. Distinguishing plain WebSocket and SockJS

| Criterion | Plain WebSocket | SockJS |
|---|---|---|
| Transport | WebSocket | WebSocket or HTTP fallback transport |
| Connection initiation | HTTP Upgrade | Endpoint info request, then transport selection |
| HTTP-only networks | May fail to connect | Can use XHR streaming or long polling |
| Application API | WebSocket API | WebSocket emulation API |
| STOMP protocol | Can run over WebSocket | Can run over SockJS transport |
| Transfer overhead | Usually lower when WebSocket works well | HTTP fallback adds requests, framing, and overhead |
| Offline message storage | Not provided natively | Not provided natively |

SockJS does not turn an unstable network connection into one with business-level delivery guarantees. It provides transport choices to improve connectivity. If message persistence, replay, or processing confirmation is required, the application must still use appropriate persistence and delivery mechanisms.

## 3. SockJS must be enabled on the server side

The Java SockJsClient needs to connect to an endpoint with SockJS enabled. With Spring STOMP, call `withSockJS()` when registering the STOMP endpoint:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOriginPatterns("https://app.example.com")
                .withSockJS();
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

In the example:

- `/ws` is the base endpoint for SockJS.
- `withSockJS()` enables the URLs and transports according to the SockJS protocol.
- `/app` is the application destination prefix for messages sent to controllers.
- `/topic` and `/queue` are broker destination prefixes in the illustrative configuration.

Replace the sample origin with the client's real origin. If the application uses Spring Security or a separate CORS layer, ensure SockJS requests are permitted through the proper security rules. HTTP fallback generates HTTP requests beyond the WebSocket handshake request, so you cannot just verify the Upgrade configuration and conclude all transports work.

**Important:** If the server only registers a plain WebSocket endpoint with `addEndpoint("/ws")` without calling `withSockJS()`, SockJsClient cannot turn that endpoint into a SockJS server on its own. Both sides must agree on the SockJS protocol.

## 4. Transports supported by Java SockJsClient

Spring's Java SockJS client supports three transport types:

| Transport | How it works | When appropriate |
|---|---|---|
| `websocket` | An HTTP Upgrade request creates a WebSocket connection; messages continue over that socket | Preferred option when the network supports it |
| `xhr-streaming` | Keeps a long HTTP request open to receive data from the server; client sends data via separate HTTP POSTs | When WebSocket cannot be used but HTTP streaming works |
| `xhr-polling` | Client holds a receive request; after each server response, the request ends and client opens a new one | Fallback option when streaming is unavailable |

One point to remember: Java SockJsClient does not support every browser-oriented transport. Transports such as iframe, htmlfile, or browser-specific techniques are not among the three transport types supported by the Java client.

### 4.1 WebSocket transport

`WebSocketTransport` uses an implementation of Spring's `WebSocketClient`. You can use:

- `StandardWebSocketClient` in runtimes supporting Jakarta WebSocket (JSR-356).
- `JettyWebSocketClient` if the application uses Jetty's WebSocket API.
- Another `WebSocketClient` implementation compatible with Spring.

When WebSocket connects successfully, messages travel over a long-lived bidirectional connection. This is usually the most efficient transport of the three options.

### 4.2 XHR transport

`XhrTransport` uses HTTP requests to emulate a WebSocket connection. From the Java client's perspective, a single XHR implementation can support both `xhr-streaming` and `xhr-polling`; the difference lies in the transport URL and how the HTTP session is maintained.

Implementations depending on the Spring version may include:

- `RestTemplateXhrTransport`: uses Spring `RestTemplate` for HTTP requests.
- `RestClientXhrTransport`: uses Spring `RestClient`, used in newer Spring Framework documentation.
- `JettyXhrTransport`: uses Jetty `HttpClient`.

Do not copy class names from one version of the documentation to another project without checking actual dependencies. Some classes are kept for compatibility or change across versions; use the Javadoc matching the Spring version you are running.

## 5. How does SockJsClient select a transport?

When starting a SockJS session, the client first sends a request to the endpoint's `/info` path. The returned information indicates the server's capabilities, such as whether the server allows WebSocket and the details needed for transport selection.

The client then selects a transport based on server capabilities and the configured list of transports. In a typical list, WebSocket is placed first and XHR is used as fallback.

Example list:

~~~java
List<Transport> transports = new ArrayList<>(2);
transports.add(new WebSocketTransport(new StandardWebSocketClient()));
transports.add(new RestTemplateXhrTransport());

SockJsClient sockJsClient = new SockJsClient(transports);
~~~

The order in the list represents the priority order the client can try. If only the WebSocket transport is declared, the application has no XHR fallback. If only the XHR transport is declared, the application does not attempt WebSocket.

### SockJS transport URLs

SockJS requests have the general structure:

~~~text
https://host:port/app/ws/{server-id}/{session-id}/{transport}
~~~

Where:

- `server-id` assists request routing in a cluster environment; beyond routing, it carries no business meaning.
- `session-id` associates HTTP requests belonging to the same SockJS session.
- `transport` identifies the transport being used, for example `websocket`, `xhr_streaming`, or `xhr`.

These are internal URLs of the SockJS protocol. Applications normally only need to provide the base endpoint such as `ws://host:port/app/ws`; SockJsClient constructs the related URLs automatically.

## 6. Combining SockJsClient with WebSocketStompClient

`SockJsClient` implements Spring's `WebSocketClient` interface. Therefore, it can be passed directly into the `WebSocketStompClient` constructor.

The example below uses `RestTemplateXhrTransport`, matching Spring Framework 6.2 examples:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.messaging.converter.StringMessageConverter;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.messaging.simp.stomp.WebSocketStompClient;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.sockjs.client.RestTemplateXhrTransport;
import org.springframework.web.socket.sockjs.client.SockJsClient;
import org.springframework.web.socket.sockjs.client.Transport;
import org.springframework.web.socket.sockjs.client.WebSocketTransport;

public class StompClientFactory {

    public WebSocketStompClient createClient() {
        List<Transport> transports = new ArrayList<>(2);

        transports.add(
                new WebSocketTransport(new StandardWebSocketClient()));

        transports.add(new RestTemplateXhrTransport());

        SockJsClient sockJsClient = new SockJsClient(transports);

        WebSocketStompClient stompClient =
                new WebSocketStompClient(sockJsClient);

        stompClient.setMessageConverter(new StringMessageConverter());

        return stompClient;
    }

    public void connect(WebSocketStompClient stompClient) {
        String url = "ws://localhost:8080/ws";

        stompClient.connect(url, new StompSessionHandlerAdapter() {
            @Override
            public void afterConnected(
                    StompSession session,
                    org.springframework.messaging.simp.stomp.StompHeaders headers) {

                // STOMP session is ready.
                // You can subscribe or send messages here.
            }
        });
    }
}
~~~

With newer Spring Framework versions that have `RestClientXhrTransport`, replace the import and constructor of `RestTemplateXhrTransport` with that class:

~~~java
import org.springframework.web.socket.sockjs.client.RestClientXhrTransport;

// ...
transports.add(new RestClientXhrTransport());
~~~

Do not declare both XHR transports simultaneously just to increase the number of fallbacks. Choose the implementation matching your project's HTTP client, dependencies, and Spring version.

### 6.1 Sending and receiving STOMP messages

After the `afterConnected` callback is invoked, you can subscribe to destinations and send messages:

~~~java
session.subscribe("/topic/updates", new StompFrameHandler() {

    @Override
    public Type getPayloadType(StompHeaders headers) {
        return String.class;
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        System.out.println("Received: " + payload);
    }
});

session.send("/app/updates", "refresh");
~~~

This example assumes the server has a controller handling `/app/updates` and broadcasting data to `/topic/updates`. If using object-shaped JSON payloads, configure an appropriate message converter such as `MappingJackson2MessageConverter` and declare the proper payload type in `getPayloadType`.

Two conversion layers must be distinguished:

- `SockJsMessageCodec` handles framing/message encoding of the SockJS protocol.
- `WebSocketStompClient`'s `MessageConverter` handles the application's STOMP payload.

By default, the SockJS Java client uses Jackson 2 for SockJS message formatting. If Jackson 2 is not on the classpath or the application needs another codec, configure an appropriate `SockJsMessageCodec` on SockJsClient. That does not replace the STOMP message converter.

## 7. Differences between XHR streaming and long polling

Both use HTTP, but how requests are held differs.

### XHR streaming

- The client opens a long HTTP request to receive data from the server.
- The server writes multiple messages into the same response following SockJS framing.
- The client sends data to the server via separate HTTP POST requests.
- The receive request can be kept open for a long time.

The advantage is not having to reopen the receive request after every message. The disadvantage is that proxies or gateways may limit response lifetime, buffer data, or close long-running requests.

### XHR long polling

- The client sends a request to wait for the server to have data.
- When the server sends a message, the response is completed.
- The client opens a new receive request.
- Client-to-server still uses separate HTTP requests.

Long polling is generally compatible with more HTTP infrastructure, but it creates extra requests and request setup overhead. When message frequency is high, overhead can be greater than streaming or WebSocket.

### General comparison

| Property | WebSocket | XHR streaming | XHR polling |
|---|---|---|---|
| Receive connection | Long-lived socket | Long HTTP response | Request ends after each data response |
| Client-to-server sending | Over socket | HTTP POST | HTTP POST |
| Request count | Few | One long receive request and send POSTs | Many receive requests and send POSTs |
| Latency | Usually low | Depends on response streaming and proxies | May increase due to polling cycle |
| Overhead | Usually lowest | Higher than WebSocket | Usually higher when messages are continuous |
| Required infrastructure support | WebSocket Upgrade | HTTP streaming | Standard HTTP request/response |

No single transport is optimal for every network. Measure in real environments, especially when reverse proxies, API gateways, firewalls, or corporate network appliances are present.

## 8. SockJS fallback is not message retry or durable delivery

Fallback only changes how connections are created and maintained. It does not provide business guarantees such as:

- Storing messages while the client is offline.
- Replaying messages after the client reconnects.
- Confirming that a message was processed by the client application.
- Deduplicating processing.
- Synchronizing missed message history.
- Persisting subscriptions across server restarts.

If a SockJS session is closed, the client needs to handle creating a new session and re-registering STOMP subscriptions. The application should have a state sync API or an event ID/version mechanism if missed notifications affect displayed data.

For example, a dashboard receives a notification that an order changed. Upon reconnecting, the client should call an API to read the latest order state. Do not assume notifications sent during offline time will be replayed by SockJS.

For critical business workflows, store state in a database or event store. A transactional outbox can be used to emit events after the business transaction commits. SockJS/WebSocket is only a notification channel to the client.

## 9. SockJS heartbeat and STOMP heartbeat

An application may simultaneously have heartbeats at multiple layers:

1. **SockJS heartbeat:** SockJS protocol frames that help keep HTTP fallback sessions alive and detect transport activity. Spring's SockJS server sends a heartbeat by default when there are no messages for a period (25 seconds according to the documented default configuration).
2. **STOMP heartbeat:** negotiated via CONNECT and CONNECTED headers. It monitors STOMP session activity.
3. **TCP/WebSocket ping-pong:** if supported by the implementation and infrastructure, this is a connection-layer mechanism.

These mechanisms do not replace each other. A SockJS heartbeat does not prove a STOMP handler processed a message. A STOMP heartbeat does not guarantee messages are durably stored. TCP ping-pong does not replace ACKs or business confirmation.

When using `WebSocketStompClient`, a `TaskScheduler` can be configured to send STOMP heartbeats:

~~~java
stompClient.setTaskScheduler(taskScheduler);
~~~

If simulating thousands of clients on one machine for load testing, note that each STOMP session may create its own heartbeat tasks. The scheduler and HTTP client must be provisioned with enough resources. For tests focused solely on throughput, heartbeats can be disabled if appropriate for the test goal; do not apply that result as production configuration when production requires heartbeats.

## 10. CORS, authentication, and proxies

HTTP fallback travels through regular HTTP requests. Therefore, check the following factors:

- **CORS:** XHR streaming and polling require proper CORS response headers if the client is on a different origin.
- **Cookies:** If authentication relies on session cookies, ensure cookies are sent in fallback HTTP requests and the SockJS server is configured appropriately.
- **Authentication headers:** If using bearer tokens or custom headers, verify whether headers are passed through the relevant SockJS requests.
- **CSRF:** HTTP requests sending data must comply with the application's and Spring Security's security policies.
- **Reverse proxy:** Configure appropriate timeouts and buffering for streaming responses; too short a timeout can cause requests to close repeatedly.
- **Load balancer:** Requests belonging to the same SockJS session must be routed to the server handling that session. Sticky sessions or server-id-based routing can be used depending on deployment architecture.

Spring's SockJS server can automatically add CORS headers for XHR transports if the response does not already have CORS headers. If the application already has a filter or gateway handling CORS, inspect the configuration to avoid duplicate or conflicting headers.

In Java SockJsClient, `setHttpHeaderNames` allows selecting which handshake headers are copied to other SockJS HTTP requests, such as `/info` or XHR send/receive requests. By API default, handshake headers are used for related requests if no specific list is configured. Only forward headers that are truly necessary and compliant with security policy.

Do not log access tokens, cookies, or sensitive content at debug/TRACE level when investigating transports.

## 11. Load, threads, and connection pools

HTTP fallback typically requires more resources than WebSocket:

- XHR streaming holds receive requests open for long periods.
- Long polling frequently creates new requests.
- Each session may require both a send request and a receive request.
- The HTTP client must have sufficient connections, threads, and appropriate timeouts.

Spring documentation notes that when using SockJsClient to simulate many concurrent users, the underlying HTTP client must be configured to allow enough connections and threads. If using `RestTemplateXhrTransport` or `RestClientXhrTransport`, inspect the corresponding request factory and connection pool configuration. If using `JettyXhrTransport`, configure Jetty HttpClient.

During testing, measure at least:

- Number of successfully connected sessions per transport.
- Fallback rate from WebSocket to XHR.
- Session creation time and reconnection time.
- Latency from server publish to client receipt.
- Number of HTTP requests and active connections.
- CPU, heap, GC, thread pool, and connection pool metrics.
- Timeouts, CORS errors, handshake errors, and number of closed sessions.

Do not measure only total WebSocket successes. The purpose of SockJS is to work when WebSocket is unavailable, so actively test fallback scenarios as well.

## 12. Error handling and reconnection

Common error categories:

| Symptom | Possible cause | What to check |
|---|---|---|
| `/info` request returns 404 | Server has not enabled SockJS or base URL is wrong | Check `withSockJS()` and endpoint |
| WebSocket handshake fails | Proxy blocks Upgrade, wrong scheme, or server disallows WebSocket | Check Upgrade request, TLS, proxy, and server logs |
| XHR streaming closes early | Proxy timeout, buffering, or response limit | Check timeouts, buffering, and gateway logs |
| XHR polling repeatedly fails | CORS, authentication, CSRF, or wrong endpoint | Check OPTIONS/GET/POST requests and response headers |
| No fallback occurs | Transport list lacks an XhrTransport or is misconfigured | Check the Transport list in order |
| STOMP CONNECT fails after transport opens | Wrong STOMP headers, authentication, or broker configuration | Read ERROR frame and message broker logs |
| Reconnected but not receiving messages | New session has not resubscribed | Re-register subscriptions after the new STOMP session connects |
| Multiple requests go to wrong node | Load balancer does not preserve routing for the SockJS session | Check sticky sessions or server-id routing |

SockJS supports fallback during transport selection when creating a session. Once a session is established and then disconnected, the application still needs a reconnection procedure. Do not assume an old STOMP session or old subscriptions automatically survive after the client opens a new SockJS session.

Application-side handling pattern:

1. Receive transport error or session-closed notification.
2. Wait using bounded backoff and add jitter so multiple clients do not reconnect simultaneously.
3. Re-establish the STOMP connection via SockJsClient.
4. Resubscribe to necessary destinations.
5. Synchronize current data via API or event cursor.
6. Resume receiving new notifications.

When using `StompSessionHandler`, you can implement `afterConnected`, `handleTransportError`, and appropriate callbacks to manage the session lifecycle.

## 13. Observability and debugging

During development, inspect actual SockJS requests:

- Initial request to `/info`.
- Selected transport URL.
- HTTP streaming or polling requests.
- Origin, Cookie, Authorization, and CORS headers.
- Response status and request lifetime.
- SockJS open, message, heartbeat, and close frames.

On the server side, TRACE logging for the `org.springframework.web.socket` package can be enabled in test environments to view transport details. Enable verbose logging only within the needed scope and avoid logging credentials.

In the browser, the SockJS JavaScript client has its own debug option. That option belongs to the JavaScript library and is not a configuration for Java `SockJsClient`.

To test each fallback individually, you can temporarily restrict configured transports in tests. For example, run one pass with WebSocket only, one pass with XHR streaming/polling only, and then run again with the full list to verify selection behavior.

## 14. When should SockJsClient be used?

SockJsClient is suitable when:

- A Java service needs to connect to a remote Spring SockJS endpoint.
- Two servers need bidirectional communication over a network with proxies restricting WebSocket.
- You need to write integration tests for a STOMP endpoint with SockJS.
- You need to simulate many concurrent clients to test connectivity and fallback.
- The system needs to keep the same STOMP client API while the transport may vary based on network capabilities.

SockJS is unnecessary if all clients and infrastructure reliably support WebSocket, there is no requirement for HTTP fallback compatibility, and the SockJS protocol is not needed. In that case, `StandardWebSocketClient` combined with `WebSocketStompClient` is usually simpler.

Do not choose SockJS merely to solve message storage or offline handling. Those requirements belong to persistence, message brokers, queues, event stores, or state-sync APIs.

## 15. Self-check exercises

### Exercise 1

The server registers the endpoint:

~~~java
registry.addEndpoint("/ws");
~~~

The client creates a `SockJsClient` and connects to `ws://localhost:8080/ws`. Why might the SockJS connection fail?

**Answer:** The endpoint has not enabled SockJS. You need to register `registry.addEndpoint("/ws").withSockJS()` so the server supports the SockJS protocol.

### Exercise 2

The transport list only contains:

~~~java
List<Transport> transports = List.of(
        new WebSocketTransport(new StandardWebSocketClient())
);
~~~

If a proxy blocks WebSocket, does Java SockJsClient have an HTTP fallback?

**Answer:** No. The list contains no `XhrTransport`, so the client has no HTTP transport to switch to.

### Exercise 3

How do `xhr-streaming` and `xhr-polling` differ?

**Answer:** Streaming keeps a long HTTP response open to receive multiple messages. Polling finishes the response after returning data and then the client opens a new receive request. Both use separate HTTP requests to send data from client to server.

### Exercise 4

After the network drops and the client creates a new STOMP session, does it need to resubscribe?

**Answer:** Yes. A new session does not automatically inherit subscriptions from the previous session. The client must re-register needed destinations and sync data that may have been missed.

### Exercise 5

Does SockJS fallback guarantee that messages sent while the client is offline will be replayed?

**Answer:** No. Fallback only changes the transport. To store and replay messages, the application needs a broker or storage supporting persistence/durable subscriptions, or a separate history API.

## 16. Production readiness checklist

- [ ] Server endpoint has `withSockJS()` enabled.
- [ ] Client list includes WebSocket transport and at least one XHR fallback when fallback is required.
- [ ] XHR implementation is compatible with the project's Spring version and HTTP client.
- [ ] URLs, TLS, CORS, cookies, authentication, and CSRF have been tested for both WebSocket and HTTP.
- [ ] Reverse proxy has suitable timeouts and buffering for streaming.
- [ ] Load balancer routes requests for the same SockJS session correctly.
- [ ] HTTP connection pool and thread pool can handle the expected number of sessions.
- [ ] Client handles reconnect, resubscribe, and state synchronization.
- [ ] Logs do not expose cookies, tokens, or sensitive payloads.
- [ ] Tested WebSocket success, XHR streaming, polling, proxy timeouts, and server restarts.

## References

- [Spring Framework — SockJS Fallback](https://docs.spring.io/spring-framework/reference/web/websocket/fallback.html)
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework 6.2 — SockJS Fallback](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/fallback.html)
- [Spring Framework Javadoc — SockJsClient](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/sockjs/client/SockJsClient.html)
- [Spring Framework Javadoc — XhrTransport](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/sockjs/client/XhrTransport.html)
- [Spring Framework Javadoc — WebSocketTransport](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/sockjs/client/WebSocketTransport.html)
