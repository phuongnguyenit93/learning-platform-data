# SockJS and Fallback Transports in Spring WebSocket

## 1. Why Is SockJS Needed?

WebSocket provides a full-duplex bidirectional connection over one TCP connection. After a successful HTTP handshake with Upgrade, the client and server exchange frames over the same connection with low latency.

However, some enterprise networks, proxies, or load balancers do not forward the Upgrade header, close a long-lived connection because they think it is idle, or apply a policy that allows only certain kinds of HTTP requests. In those environments, plain WebSocket may fail to connect even though the browser supports the protocol.

SockJS solves the compatibility problem by emulating the WebSocket API. The client tries WebSocket first; if that transport is unavailable, the client automatically selects an HTTP streaming or HTTP long polling technique. The application still works with the same application-level API, so the message-handling code usually does not need to change depending on the selected transport.

Spring Framework provides a SockJS server and a Java client in the spring-websocket module. On the browser side, the application uses the sockjs-client library. SockJS can be used with a plain WebSocketHandler or as the transport for STOMP messaging.

You need to distinguish three layers:

- **WebSocket:** a protocol for transmitting frames in both directions.
- **SockJS:** an emulation protocol and transport selector to maintain a WebSocket-like API when WebSocket cannot be used.
- **STOMP:** a messaging protocol that runs on top of WebSocket or SockJS, providing SEND, SUBSCRIBE, MESSAGE, and other messaging commands.

SockJS is not a message broker, does not define business destinations on its own, and does not replace STOMP.

## 2. How Does SockJS Select a Transport?

When the client starts connecting, it sends an HTTP GET to the endpoint with the path /info. The server returns the information the client needs to decide on a transport, such as whether WebSocket is enabled and whether the application needs a session cookie.

The client then chooses based on the browser's capabilities and the network environment:

1. Use WebSocket if the handshake can be performed.
2. If WebSocket cannot be used, try an appropriate HTTP streaming transport.
3. If streaming is also unavailable, switch to HTTP long polling.

The selection happens at runtime. The same application may use WebSocket on one network and XHR streaming or long polling on another.

SockJS requests typically have the structure:

~~~text
https://host:port/app/endpoint/{server-id}/{session-id}/{transport}
~~~

Where:

- server-id helps route requests in a cluster environment; the application can use it to support sticky routing.
- session-id links the HTTP requests belonging to the same SockJS session.
- transport indicates the technique in use, for example websocket, xhr-streaming, or xhr-polling.

With the WebSocket transport, the client only needs one handshake request; subsequent messages go through that socket. With HTTP transports, a SockJS session can create many requests and the server needs to link them by session-id.

## 3. The Three Main Transport Groups

Spring divides the SockJS transports into three groups: WebSocket, HTTP Streaming, and HTTP Long Polling.

### 3.1. WebSocket Transport

This is the preferred choice when the environment allows the Upgrade handshake and keeps long-lived connections.

- One HTTP handshake switches the connection to WebSocket.
- The client and server send frames in both directions on the same socket.
- No new HTTP request has to be opened for each message.
- Latency and overhead are usually lower than the HTTP fallbacks.

If WebSocket works reliably through proxies and load balancers, the SockJS client usually chooses this transport.

### 3.2. HTTP Streaming

HTTP streaming keeps one request that receives data from the server open for a long time. The server writes more data into the response when there is a new message. The client sends data to the server using separate HTTP POST requests.

Common transports in this group include xhr-streaming, eventsource, and some iframe techniques for older browsers.

Characteristics:

- A receiving request can exist for a long time.
- Client-to-server typically uses a separate POST.
- The server can send many messages on the same streaming response.
- When the response reaches the byte limit or the connection is closed, the client creates a new request to continue the session.

HTTP streaming reduces the number of receiving requests compared with polling. However, proxies may buffer the response or close long-lived requests; you need to test with real infrastructure.

### 3.3. HTTP Long Polling

Long polling uses a chain of receiving requests:

1. The client sends a GET to wait for the server to have a message.
2. The server holds the request open until there is a message or the wait times out.
3. The server returns a response and ends the request.
4. The client immediately opens the next GET request.
5. The client sends data to the server through a separate HTTP POST.

Long polling is compatible with more proxies and HTTP infrastructure, but it creates more requests, headers, and HTTP setups. When there are no messages, the client still has to reopen the request periodically.

A common transport is named xhr-polling or xhr. Some older browsers use iframe-xhr-polling or jsonp-polling.

## 4. Common Specific Transports

Transport names depend on the browser and the sockjs-client version. Commonly seen names include:

| Group | Transport name | How it works |
| --- | --- | --- |
| WebSocket | websocket | A standard WebSocket connection |
| HTTP Streaming | xhr-streaming | XHR keeps the response open to receive many messages |
| HTTP Streaming | eventsource | Based on Server-Sent Events for the server-to-client direction, combined with separate sending requests |
| HTTP Streaming | htmlfile, iframe-eventsource, iframe-htmlfile | Fallback techniques for some older browsers |
| HTTP Long Polling | xhr, xhr-polling | A GET waits for a message and then ends; the client opens the next request |
| HTTP Long Polling | iframe-xhr-polling | Long polling via an iframe |
| HTTP Long Polling | jsonp-polling | An old polling technique based on JSONP |
| HTTP Streaming/Polling | xdr-streaming, xdr-polling | Uses XDomainRequest on some older IE browsers |

Not every browser supports every transport. The SockJS client has its own compatibility matrix and chooses the available methods itself. When investigating errors, look at the actual transport in the Network tab instead of assuming every client uses WebSocket.

The Spring SockJS Java client has a narrower set of transports than the browser client: it supports websocket, xhr-streaming, and xhr-polling. The iframe and JSONP techniques mainly serve older browsers.

## 5. Comparing WebSocket, Streaming, and Long Polling

| Criterion | WebSocket | HTTP Streaming | HTTP Long Polling |
| --- | --- | --- | --- |
| Receiving connection | One long-lived socket | One long-open HTTP response | Many sequential GET requests |
| Sending data to the server | Frames on the same socket | Separate HTTP POST | Separate HTTP POST |
| Request overhead | Low after the handshake | Medium | Higher due to many requests |
| Proxy traversal | Depends on Upgrade and the socket policy | Depends on whether the proxy allows streaming responses | Usually more broadly compatible |
| Latency | Low | Low to medium | Depends on the request cycle |
| Server resources | Holds a WebSocket session | Holds a streaming request/response | Continuously opens and ends requests |
| Suitable case | Networks that support WebSocket | WebSocket is blocked but streaming works | Streaming is blocked or the environment only supports request-response |

A fallback increases the ability to connect but usually comes with costs in requests, headers, buffering, threads, or HTTP resources. Treat the selected transport as an operational characteristic to monitor.

## 6. SockJS Framing

SockJS adds a small framing layer to represent the session state and the list of messages across different transports.

Some typical frames:

| Frame | Meaning |
| --- | --- |
| o | Opens the SockJS session |
| a["message1","message2"] | A JSON array containing the application messages |
| h | The SockJS heartbeat |
| c[code,"reason"] | Closes the session with a code and reason |

Example of the server sending two messages:

~~~text
a["first message","second message"]
~~~

The SockJS client decodes this framing and then passes the messages to a callback like the WebSocket API. The application usually does not need to parse the o, a, h, or c frames itself.

With STOMP over SockJS, inside a SockJS message there is also a STOMP frame. SockJS handles transport emulation; STOMP handles messaging commands and destinations.

Do not send raw WebSocket frames directly into a STOMP/SockJS endpoint on the assumption that the two protocols have the same framing. The client and server must use the correct corresponding libraries and sub-protocol.

## 7. Enabling SockJS for a Plain WebSocketHandler

If the application uses a plain WebSocketHandler, you can enable SockJS directly on the handler mapping with withSockJS():

~~~java
@Configuration
@EnableWebSocket
public class RawWebSocketConfiguration implements WebSocketConfigurer {

    @Bean
    public WebSocketHandler echoHandler() {
        return new EchoWebSocketHandler();
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler(), "/ws/raw")
                .setAllowedOrigins("https://app.example.com")
                .withSockJS();
    }
}
~~~

The echoHandler bean is registered in the Spring context and used for the /ws/raw endpoint. This endpoint accepts WebSocket or the SockJS transports that the client may choose.

The handler still receives the WebSocketHandler callbacks such as afterConnectionEstablished, handleMessage, and afterConnectionClosed. Spring SockJS maps the fallback transports back to the same session/handler model for the application to handle.

The example assumes EchoWebSocketHandler has been implemented. You need to configure component scanning or declare the bean as above so that Spring can use the handler.

## 8. Enabling SockJS for a STOMP Endpoint

If the application uses high-level Spring messaging, enable SockJS on the STOMP endpoint:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com")
                .withSockJS();
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

The client connects to /ws. The SockJS client will choose WebSocket or an HTTP fallback; the STOMP client continues to exchange CONNECT, SEND, SUBSCRIBE, and MESSAGE over the chosen transport.

JavaScript example with @stomp/stompjs and sockjs-client:

~~~javascript
import { Client } from "@stomp/stompjs";
import SockJS from "sockjs-client";

const client = new Client({
    webSocketFactory: () => new SockJS("/ws"),
    reconnectDelay: 5000,
    onConnect: () => {
        client.subscribe("/topic/updates", frame => {
            console.log(frame.body);
        });
    }
});

client.activate();
~~~

webSocketFactory returns a SockJS object for the STOMP client. When the connection succeeds, the client subscribes to /topic/updates. If the current transport is lost, reconnectDelay lets the STOMP client try to reconnect; the application needs to re-register subscriptions in onConnect.

Do not create a SockJS object once and reuse it across multiple reconnects. The factory is called to create a new transport instance for each connection.

## 9. Configuring Limits and Timings on the Server

Spring lets you customize the SockJS properties through the object returned from withSockJS().

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.com")
            .withSockJS()
            .setHeartbeatTime(25_000)
            .setDisconnectDelay(5_000)
            .setStreamBytesLimit(128 * 1024)
            .setHttpMessageCacheSize(100)
            .setSessionCookieNeeded(true);
}
~~~

The values in the example correspond to the common Spring defaults:

| Property | Default | Role |
| --- | --- | --- |
| heartbeatTime | 25 seconds | The interval for sending a heartbeat when there is no other message |
| disconnectDelay | 5 seconds | The wait time to receive the next request before considering an HTTP-based session disconnected |
| streamBytesLimit | 128 KiB | The minimum number of bytes sent on one HTTP streaming response before the response is closed and the client opens a new request |
| httpMessageCacheSize | 100 | The number of messages cached for the HTTP transport/session |
| sessionCookieNeeded | true | Tells the client that the application needs a session cookie, for example JSESSIONID |

Do not arbitrarily increase streamBytesLimit or httpMessageCacheSize. Streaming keeps the response open and may keep sent data in memory on the client side; a larger cache also increases server memory for HTTP sessions. Adjust according to message size, the number of concurrent sessions, and memory limits.

If you need to control the heartbeat sending schedule, you can configure a separate TaskScheduler. The scheduler needs enough threads for the number of sessions and the expected heartbeat rate.

## 10. Heartbeat and Detecting a Client That Lost Its Connection

A heartbeat helps proxies and load balancers avoid treating a connection that has had no data for a long time as dead.

By default, Spring SockJS sends a heartbeat after 25 seconds if no other message is sent on the connection. When there are application messages, a heartbeat is not needed within that interval.

When using STOMP over SockJS:

- If the client and server negotiate a STOMP heartbeat, the SockJS heartbeat is turned off.
- The STOMP heartbeat then takes over checking the exchange flow.
- If the STOMP heartbeat is not negotiated, the SockJS heartbeat is still used per the configuration.

With HTTP streaming and long polling, the Servlet API does not always notify immediately when a client has left the network. Spring can detect a disconnect when the next response write fails; a heartbeat helps detect this case sooner.

A response write failure after the client disconnects is an operational situation that can occur. Spring tries to recognize the corresponding network error and writes minimal logs. You can enable TRACE for the SockJS log category when you need a deeper investigation.

## 11. CORS, Origin, and Session Cookies

HTTP streaming and long polling use HTTP requests and are therefore affected by CORS. Spring SockJS automatically adds the necessary CORS headers when the corresponding headers are not already provided by another layer. If the application has already configured CORS through a Servlet Filter or a security layer, SockJS can detect that and skip the headers that already exist.

A few points to note:

- Configure allowed origins according to the actual frontend domain.
- Do not use CORS as an authentication or authorization mechanism.
- For requests with credentials, cookies and sessions must be handled consistently.
- sessionCookieNeeded defaults to true because many Java applications need JSESSIONID for the HTTP session or sticky session.
- If the application does not need a session cookie, you can consider setting sessionCookieNeeded(false) so the client has more transport choices on some older browsers.

When allowed origins are restricted, some iframe or JSONP transports that do not send an Origin header may be disabled. This can leave some older browsers without a suitable transport.

### 11.1. Iframe Transport and X-Frame-Options

Some older transports use an iframe to perform cross-domain communication. If the response sets X-Frame-Options: DENY, the browser will block the iframe.

If you still need an iframe transport for older clients, you need to configure a frame policy appropriate to the architecture and security policy, for example SAMEORIGIN when the iframe is same-origin. Do not loosen X-Frame-Options just to make the fallback work if there is no need to support that transport.

Spring SockJS also lets you set the client library URL for the iframe. In a production environment, you should serve the SockJS client library from the same origin if appropriate to the application's CSP and cache policy.

## 12. SockJS in Cluster and Load Balancer Environments

A SockJS session can consist of many HTTP requests, especially with streaming and long polling. Those requests must be linked to the same session-id.

In a multi-instance environment:

- Use the server-id in the URL to support routing if the load balancer needs it.
- Configure sticky sessions so that requests of the same SockJS session reach the instance that is holding the session.
- Ensure the proxy/load balancer timeout is compatible with the heartbeat and the request hold time.
- Verify that the HTTP POST that sends messages and the GET that receives messages are both routed to the appropriate instance.
- When an instance restarts, the client needs to reconnect and create a new session.

The simple in-memory session state of one instance is not automatically shared with another instance. If you need multiple nodes, you must design routing, sticky sessions, or an appropriate messaging/broker infrastructure. A broker relay solves distributing STOMP messages among nodes according to the broker configuration, but it does not by itself replace the requirement to route HTTP requests belonging to the same SockJS session.

## 13. The Java-Side SockJsClient

Spring provides SockJsClient to connect to a SockJS server from a Java application without a browser. This client is useful for server-to-server integration, testing, or simulating many connections.

Spring's SockJsClient supports the transports:

- WebSocketTransport, which can use StandardWebSocketClient in a JSR-356 runtime or another Spring WebSocketClient.
- XhrTransport, which supports both xhr-streaming and xhr-polling.
- RestClientXhrTransport uses Spring RestClient for HTTP requests.
- JettyXhrTransport uses the Jetty HttpClient.

Example of creating a client:

~~~java
List<Transport> transports = new ArrayList<>();
transports.add(new WebSocketTransport(new StandardWebSocketClient()));
transports.add(new RestClientXhrTransport());

SockJsClient sockJsClient = new SockJsClient(transports);
sockJsClient.doHandshake(new MyWebSocketHandler(), "ws://example.com:8080/sockjs");
~~~

MyWebSocketHandler is the application's WebSocketHandler. To run the example you need the spring-websocket dependency, the corresponding client transport library, and a working SockJS endpoint.

When simulating many concurrent users with the XHR transport, you need to configure an HTTP client with enough connections and threads. If the HTTP client only allows a small number of connections to the same host, the simulated sessions may queue up or time out even though the server still has capacity to handle them.

## 14. Limits and Costs of the Fallback

SockJS improves compatibility, but the HTTP fallback has some costs:

- More requests and headers than WebSocket.
- Streaming keeps the response open and can be buffered by a proxy.
- Long polling creates a new request after each message received.
- The client and server need to manage the session across many requests.
- CORS, cookies, sticky sessions, and proxy timeouts are more complex.
- Latency and throughput depend on the selected transport.
- The HTTP fallback does not make every network environment work; a firewall or proxy may block even the necessary HTTP requests.

Measure the number of sessions per transport, the number of polling requests, the streaming response time, heartbeats, reconnects, and network errors. Do not only monitor the total number of WebSocket connections because the fallback sessions may not create real WebSocket connections.

## 15. How to Check Which Transport Is in Use

You can check from the browser:

1. Open Developer Tools and choose Network.
2. Find the /info request to see whether the client obtained the SockJS information.
3. Observe the transport URL afterward, for example websocket, xhr_streaming, or xhr.
4. Check the long-lived GET request and the POST that sends messages if an HTTP fallback is in use.
5. Monitor the HTTP codes, response time, CORS headers, cookies, and reconnects.

On the server side, enable TRACE for the package org.springframework.web.socket to see the details of the transport and session. In a production environment, only enable detailed logging during the investigation because logs can contain a lot of connection information.

If the client chooses polling when WebSocket should work, check the proxy Upgrade header, TLS termination, the load balancer idle timeout, and the endpoint configuration. If the client cannot connect even through the fallback, check /info, CORS, authentication, cookies, and the routing of the session.

## 16. Common Mistakes

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| /info returns 404 | The SockJS endpoint is not registered or the context path is wrong | Check addHandler/addEndpoint and withSockJS |
| WebSocket fails but the client does not fall back | The SockJS client is not being used or the transport list is restricted | Use sockjs-client and check the transport configuration |
| XHR streaming is open but receives no messages | The proxy buffers the response or a timeout closes the request | Check proxy buffering, heartbeat, and streamBytesLimit |
| Long polling creates too many requests | The client keeps opening the next receiving request | This is a characteristic of polling; evaluate using streaming/WebSocket |
| Client cannot send cookies | An old transport does not support cookies or credentials/CORS is wrong | Check sessionCookieNeeded, credentials, and a compatible transport |
| Iframe transport is blocked | X-Frame-Options or CSP blocks the iframe | Only allow an appropriate frame policy if that transport is still needed |
| Client disconnects after an idle period | A proxy or load balancer closes a connection with no data for a long time | Configure an appropriate heartbeat and idle timeout |
| Client keeps creating new sessions | Requests of the same session are routed to another instance or disconnectDelay is too short | Configure sticky sessions and check the load balancer |
| Server does not detect that the client has left | HTTP streaming has no immediate disconnect notification | Use a heartbeat and monitor response write errors |
| STOMP client connects but does not receive the subscription | Confusing the fallback transport with the destination or subscription | Check STOMP CONNECT, SUBSCRIBE, and the broker destination |
| Increasing the cache causes out-of-memory | httpMessageCacheSize or streamBytesLimit is too large | Measure memory/session and set appropriate limits |
| The SockJS Java client runs out of connections | The HTTP client does not have enough connections/threads for the number of sessions | Increase the connection limit and an appropriate executor |

## 17. Deployment Checklist

- [ ] Determine whether you really need to support environments that cannot use WebSocket.
- [ ] Enable withSockJS() on the correct raw handler or STOMP endpoint.
- [ ] Use sockjs-client in the browser when the endpoint requires SockJS.
- [ ] Check the /info request and the actual transport.
- [ ] Test WebSocket, HTTP streaming, and long polling in the target network environment.
- [ ] Configure a heartbeat appropriate to the proxy/load balancer idle timeout.
- [ ] Set streamBytesLimit, httpMessageCacheSize, and disconnectDelay according to the actual load.
- [ ] Configure CORS, allowed origins, cookies, and credentials correctly.
- [ ] If using a cluster, configure sticky routing for the same SockJS session.
- [ ] Check X-Frame-Options if you still support an iframe transport.
- [ ] Configure reconnect and resubscribe on the client.
- [ ] Monitor the number of sessions per transport, polling rate, reconnects, heartbeats, and network errors.
- [ ] Limit message size, the number of sessions, and the send rate to protect server resources.

## 18. References

- [Spring Framework 7.0.10 — SockJS Fallback](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/fallback.html)
- [Spring Framework 7.0.10 — WebSocket API](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/server.html)
- [Spring Framework 7.0.10 — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp.html)
- [SockJS Protocol](https://github.com/sockjs/sockjs-protocol)
- [SockJS Client — Supported Transports](https://github.com/sockjs/sockjs-client)
- [Spring Framework API — SockJsClient](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/sockjs/client/SockJsClient.html)
- [Spring Framework API — SockJsServiceRegistration](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/config/annotation/SockJsServiceRegistration.html)
