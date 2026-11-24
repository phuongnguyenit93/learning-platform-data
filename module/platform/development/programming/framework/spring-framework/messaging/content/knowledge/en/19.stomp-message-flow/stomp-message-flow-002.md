# registerStompEndpoints and the Client Connection Path

## Objectives

In Spring STOMP over WebSocket, the server must expose an endpoint for clients to perform the HTTP handshake and upgrade the connection to WebSocket. Spring configures this endpoint through the **registerStompEndpoints(StompEndpointRegistry registry)** method of **WebSocketMessageBrokerConfigurer**.

The endpoint path is the connection URL at the transport layer. Only after connecting successfully does the client send STOMP frames such as **CONNECT**, **SUBSCRIBE**, and **SEND**. The endpoint path is therefore different from the destinations that STOMP uses to route messages.

After this lesson, you can:

- Enable STOMP over WebSocket infrastructure in Spring.
- Register one or more endpoints with **registerStompEndpoints**.
- Determine the URL the client needs to connect to when there is a server port, context path, and reverse proxy.
- Distinguish the WebSocket endpoint path from STOMP application/broker destination prefixes.
- Connect using direct WebSocket or SockJS fallback.
- Configure allowed origins, handshake interceptors, and connection security.
- Diagnose URL, handshake, STOMP CONNECT, and subscription errors.

## 1. WebSocket and STOMP handle two different layers

WebSocket provides a long-lived two-way connection between client and server. WebSocket itself only defines how frames are transmitted; it does not prescribe application message content.

STOMP is a messaging protocol that runs on top of WebSocket. STOMP defines frames and headers such as:

| STOMP frame | Purpose |
|---|---|
| CONNECT | The client starts a STOMP session |
| CONNECTED | The server confirms the STOMP session |
| SUBSCRIBE | The client registers to receive messages from a destination |
| SEND | The client sends a message to a destination |
| MESSAGE | The server/broker sends a message to a subscriber |
| UNSUBSCRIBE | The client cancels a subscription |
| DISCONNECT | The client ends the session |

A connection session has two phases:

~~~text
Client                         Spring server
  |                                  |
  | 1. HTTP GET + Upgrade            |
  |--------------------------------->|
  | 2. HTTP 101 Switching Protocols  |
  |<---------------------------------|
  |                                  |
  | 3. STOMP CONNECT                 |
  |--------------------------------->|
  | 4. STOMP CONNECTED               |
  |<---------------------------------|
  |                                  |
  | 5. SUBSCRIBE / SEND              |
  |<-------------------------------->|
  |                                  |
  | 6. DISCONNECT                    |
  |--------------------------------->|
~~~

**registerStompEndpoints** configures step 1 and step 2. STOMP frames are exchanged only after the WebSocket or SockJS transport has been established.

## 2. Enabling STOMP infrastructure in Spring

STOMP over WebSocket is provided by two modules: **spring-messaging** and **spring-websocket**. The application needs the corresponding dependencies and must enable **@EnableWebSocketMessageBroker**.

Basic configuration example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/stomp");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry config) {
        config.setApplicationDestinationPrefixes("/app");
        config.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

The two methods have separate responsibilities:

- **registerStompEndpoints(...)**: registers the endpoint URL for clients to start the handshake.
- **configureMessageBroker(...)**: configures how Spring routes STOMP destinations after the connection has been established.

**@EnableWebSocketMessageBroker** imports the infrastructure needed for Spring to detect endpoints, manage WebSocket sessions, and convert STOMP frames into Spring Messages.

## 3. Registering endpoints with registerStompEndpoints

Method signature:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/stomp");
}
~~~

**registry.addEndpoint("/stomp")** registers an endpoint with the path **/stomp**. This is the path part used for the HTTP handshake. If the server runs at **http://localhost:8080**, the application has no context path, and no extra prefix is placed at a reverse proxy, the client connects with:

~~~text
ws://localhost:8080/stomp
~~~

When the server is accessed over HTTPS, the client must use secure WebSocket:

~~~text
wss://example.com/stomp
~~~

Endpoints can register multiple paths if the application needs multiple connection points:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/stomp");
    registry.addEndpoint("/admin-stomp");
}
~~~

Each path is a separate handshake URL. Allowed origins, handshake handlers, or interceptors can be configured separately for each endpoint.

There is no need to create a separate endpoint for each STOMP destination. A single **/stomp** endpoint can serve many destinations such as **/app/chat.send**, **/topic/public**, and **/queue/notifications**.

## 4. How is the client connection path formed?

The URL the client needs to connect to depends on several parts:

~~~text
scheme://host:port/context-path/endpoint-path
~~~

| Part | Example | Configuration source |
|---|---|---|
| Scheme | ws or wss | External HTTP/HTTPS and TLS |
| Host | localhost, api.example.com | Domain the client accesses |
| Port | 8080, 443 | Server or reverse proxy |
| Context path | /messaging | Servlet/application context |
| Endpoint path | /stomp | registry.addEndpoint("/stomp") |

Example:

- The server runs on port **8080**.
- The application context path is **/messaging**.
- The registered endpoint is **/stomp**.
- The client accesses the same machine in a local environment.

The connection URL is:

~~~text
ws://localhost:8080/messaging/stomp
~~~

When deploying HTTPS on a public domain:

~~~text
wss://api.example.com/messaging/stomp
~~~

The context path is prepended to the URL outside the endpoint path. Spring does not automatically add **/app**, **/topic**, or **/queue** to the handshake URL.

If the frontend and backend share the same origin, use a relative URL for SockJS or build the WebSocket URL from the current location to avoid hard-coding hosts across environments. If the frontend and backend have different origins, configure allowed origins and the full URL accordingly.

## 5. An endpoint path is not a STOMP destination prefix

This is a very common point of confusion.

Suppose the configuration is:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/stomp");
}

@Override
public void configureMessageBroker(MessageBrokerRegistry config) {
    config.setApplicationDestinationPrefixes("/app");
    config.enableSimpleBroker("/topic", "/queue");
}
~~~

Meaning:

| Path | Where is it used? | Example |
|---|---|---|
| /stomp | HTTP/WebSocket handshake URL | ws://localhost:8080/stomp |
| /app | Prefix of STOMP SENDs entering controllers | /app/chat.send |
| /topic | Destination prefix for subscribing via the simple broker | /topic/public |
| /queue | Destination prefix by point-to-point convention | /queue/notifications |

Example processing flow:

1. The client connects to **ws://localhost:8080/stomp**.
2. The client sends STOMP **SUBSCRIBE** to **/topic/public**.
3. The client sends STOMP **SEND** to **/app/chat.send**.
4. Spring strips the **/app** prefix and looks up the **@MessageMapping("/chat.send")** method.
5. The controller result is sent to the appropriate broker destination.
6. The broker forwards the message to clients subscribed to **/topic/public**.

**/topic** and **/queue** in Spring's built-in simple broker are only naming conventions to distinguish pub/sub and point-to-point. When using an external broker relay, check the destinations and prefixes that the broker actually supports.

## 6. Connecting from a browser with STOMP.js

Spring recommends using the **@stomp/stompjs** library for modern JavaScript clients.

Install the package in the frontend:

~~~bash
npm install @stomp/stompjs
~~~

Example of a direct WebSocket connection:

~~~javascript
import { Client } from '@stomp/stompjs';

const client = new Client({
    brokerURL: 'ws://localhost:8080/stomp',
    reconnectDelay: 5000,

    onConnect: () => {
        console.log('STOMP connected');

        client.subscribe('/topic/public', (frame) => {
            const message = JSON.parse(frame.body);
            console.log('Received:', message);
        });

        client.publish({
            destination: '/app/chat.send',
            body: JSON.stringify({
                from: 'alice',
                text: 'Hello Spring STOMP'
            })
        });
    },

    onStompError: (frame) => {
        console.error('STOMP broker error:', frame.headers['message']);
        console.error(frame.body);
    },

    onWebSocketError: (event) => {
        console.error('WebSocket transport error:', event);
    }
});

client.activate();
~~~

**brokerURL** is the transport URL, for example **ws://localhost:8080/stomp**. In production with HTTPS, use **wss://**:

~~~javascript
brokerURL: 'wss://api.example.com/messaging/stomp'
~~~

**reconnectDelay** sets the wait interval before STOMP.js tries to reconnect after losing the connection. The **onConnect** callback is called after each successful connection, so subscriptions should be created inside this callback to be re-registered after a reconnect.

When a component or page no longer needs the connection, call:

~~~javascript
await client.deactivate();
~~~

Closing the STOMP client frees the WebSocket session and avoids keeping unnecessary connections open.

## 7. Connecting through SockJS fallback

Some proxies or corporate networks block WebSocket Upgrade or close idle connections. SockJS provides alternative HTTP-based transports such as streaming and long polling.

Enable SockJS on the server:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/stomp").withSockJS();
}
~~~

The client uses **sockjs-client** as the WebSocket factory:

~~~bash
npm install @stomp/stompjs sockjs-client
~~~

~~~javascript
import { Client } from '@stomp/stompjs';
import SockJS from 'sockjs-client';

const client = new Client({
    webSocketFactory: () => new SockJS('/stomp'),
    reconnectDelay: 5000,

    onConnect: () => {
        console.log('STOMP connected through SockJS');

        client.subscribe('/topic/public', (frame) => {
            console.log('Received:', frame.body);
        });
    },

    onStompError: (frame) => {
        console.error('STOMP error:', frame.headers['message']);
    }
});

client.activate();
~~~

With SockJS, pass the base endpoint URL to **new SockJS(...)**. Do not manually append **/websocket**, a server ID, a session ID, or a transport suffix. The SockJS client calls **/info** on its own, selects a transport, and constructs the necessary HTTP URLs.

If the application has the context path **/messaging**, a same-origin client uses:

~~~javascript
webSocketFactory: () => new SockJS('/messaging/stomp')
~~~

If the frontend is on another domain, use a full HTTPS URL and configure allowed origins/CORS appropriately for SockJS transports.

SockJS does not change STOMP destinations. After the transport connects, the client still sends **SUBSCRIBE /topic/public** and **SEND /app/chat.send** just as when using WebSocket directly.

## 8. Complete example of an endpoint and message destination

Server configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/stomp");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry config) {
        config.setApplicationDestinationPrefixes("/app");
        config.enableSimpleBroker("/topic");
    }
}
~~~

DTO:

~~~java
public record ChatMessage(String from, String text) {
}
~~~

Controller:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/public")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

Client connects to the transport:

~~~text
ws://localhost:8080/stomp
~~~

Client sends a message:

~~~text
SEND
destination:/app/chat.send

{"from":"alice","text":"Hello"}
~~~

Client subscribes to receive:

~~~text
SUBSCRIBE
id:public-subscription
destination:/topic/public

~~~

When the client sends to **/app/chat.send**, Spring routes to **ChatController.send**. The return value is published to **/topic/public**; every client subscribed to that destination receives the message.

This example consists of integration components inside a Spring application, requiring the **spring-messaging** and **spring-websocket** dependencies, web server configuration, and a frontend STOMP client. You cannot run the controller alone with **javac** without a Spring application context.

## 9. Allowed origins and the handshake

A WebSocket endpoint begins with an HTTP request. From a browser, the request usually carries an **Origin** header. Spring checks the origin to restrict external websites from opening connections on behalf of a logged-in user.

By default, Spring allows only the same origin. If the frontend and backend run on two different origins, add the specific origin:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/stomp")
            .setAllowedOrigins("https://app.example.com");
}
~~~

An origin includes the scheme, host, and port if present. Do not add a path such as **/dashboard** to the origin.

You should not configure **\*** for production without a clear reason. Checking the Origin helps protect browser sessions, but it does not replace authentication: a non-browser client can send an Origin header itself. The server still must authenticate users and authorize messages.

Allowed origins also differ from CORS configuration for REST APIs. When using SockJS, HTTP streaming/polling transports may need CORS headers; Spring's SockJS service has support mechanisms for those transports.

## 10. Handshake interceptors and session information

**StompEndpointRegistration** lets you add a **HandshakeInterceptor**:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/stomp")
            .addInterceptors(handshakeInterceptor());
}
~~~

A handshake interceptor runs around the start of the WebSocket handshake. It can:

- Inspect information in the HTTP request.
- Place needed attributes into WebSocket session attributes.
- Record data for tracing or auditing.
- Reject the handshake if the application's conditions are not met.

The example above assumes **handshakeInterceptor()** is a bean or method returning an application-provided **HandshakeInterceptor** implementation.

Do not use an interceptor to replace authorization for individual STOMP messages. A user can connect successfully and still not be allowed to send to or subscribe to a specific destination.

## 11. Authentication and authorization for STOMP

In Spring WebSocket, the **Principal** authenticated on the HTTP handshake request is attached to the WebSocket session. If the application uses Spring Security, the usual approach is to authenticate HTTP before the client opens the WebSocket.

Some important points:

- The **login** and **passcode** headers of STOMP **CONNECT** are ignored or overridden by Spring by default for STOMP over WebSocket.
- You can use the HTTP session/cookie or an existing HTTP authentication mechanism.
- If a token is needed in STOMP **CONNECT**, the application must configure an interceptor on the inbound channel to validate the token header according to its own design.
- With **@EnableWebSocketSecurity**, Spring Security requires a CSRF token on inbound **CONNECT** by default.
- Permissions must be configured separately for **SEND** and **SUBSCRIBE** frames.

Example of an authorization policy that should distinguish:

| Frame | Example destination | Permission to check |
|---|---|---|
| SEND | /app/chat.send | Is the user allowed to send messages to the chat feature? |
| SUBSCRIBE | /topic/public | Is the user allowed to view the public channel? |
| SUBSCRIBE | /user/queue/notifications | Is the user allowed to receive their own personal messages? |
| SEND | /topic/system/notifications | Should clients be blocked from sending directly to a server-only destination? |

Do not trust sender identity data sent by the client in the payload. The server should take the user from the authenticated **Principal** and attach that identity to the business message.

## 12. Context path, reverse proxy, and TLS

A client URL may work locally but fail when deployed because a context path or reverse proxy changes the external path.

Example:

- The Spring application has **server.servlet.context-path=/messaging**.
- The endpoint is registered with **registry.addEndpoint("/stomp")**.
- The reverse proxy exposes the application at **https://example.com/messaging**.

The client must connect to:

~~~text
wss://example.com/messaging/stomp
~~~

When deploying behind Nginx, Apache, or a load balancer:

- The proxy must forward HTTP Upgrade and the **Upgrade**/**Connection** headers for WebSocket.
- Use **wss://** when the web page is served over HTTPS.
- Preserve the context path or configure a corresponding rewrite.
- Configure timeouts for long-lived connections.
- If running multiple instances, check routing/sticky sessions and how the broker shares subscriptions.
- If the proxy terminates TLS, ensure the external scheme used by clients is **wss**.

With SockJS, the proxy must also forward the HTTP requests of streaming/polling transports to the same endpoint.

## 13. Diagnosing connection errors

| Symptom | Possible cause | How to check |
|---|---|---|
| HTTP 404 when connecting | Wrong endpoint path or missing context path | Compare the client URL with addEndpoint and the context path |
| HTTP 403 during handshake | Disallowed origin or Spring Security rejection | Check Origin, authentication, CSRF, and security filters |
| HTTP 400/426 or no Upgrade | Proxy/server not forwarding WebSocket Upgrade | Check Upgrade, Connection, and proxy configuration |
| WebSocket opens but STOMP CONNECT fails | Client/server disagree on STOMP protocol or auth/CSRF failure | Inspect the ERROR frame, server logs, and CONNECT headers |
| Connection succeeds but no messages arrive | Subscribed to wrong destination or broker prefix | Check SUBSCRIBE and enableSimpleBroker |
| @MessageMapping is not invoked | Client SENDs to wrong application prefix | Check /app and the method mapping |
| Works locally, fails on HTTPS | Client uses ws:// from an HTTPS page | Switch to wss:// or HTTPS SockJS |
| SockJS /info returns 404 | Client uses wrong base URL or server has not enabled withSockJS | Check the endpoint path and base URL |
| Reconnects but receives no messages | Subscriptions not recreated after reconnect | Register subscriptions inside onConnect |
| Browser reports CORS/origin error | Frontend on different origin or SockJS HTTP transport not configured | Check allowed origins and CORS responses |

When debugging, check in order: HTTP handshake, STOMP CONNECT/CONNECTED, SUBSCRIBE, SEND, and MESSAGE. A successful WebSocket connection does not prove that the STOMP session or subscriptions are working.

## 14. Testing the endpoint

You should test both the transport URL and the message flow:

1. Start the application and confirm the handshake endpoint returns success.
2. Use a STOMP client to connect to the exact URL with the context path.
3. Confirm receiving the **CONNECTED** frame.
4. Subscribe to a destination such as **/topic/public**.
5. Send a message to **/app/chat.send**.
6. Confirm the **@MessageMapping** controller is invoked.
7. Confirm the subscriber receives the **MESSAGE** frame.
8. Try connecting from a disallowed origin and confirm it is rejected.
9. If SockJS is enabled, test the WebSocket transport and an HTTP fallback transport.
10. Test network loss, reconnect, and confirm subscriptions are recreated.

You can use Spring's **WebSocketStompClient** in integration tests or **@stomp/stompjs** in the browser. When testing through a proxy, use the external URL that production clients actually use.

## 15. Common mistakes

- **Using /app as the WebSocket URL:** /app is usually STOMP's application destination prefix. The handshake URL must be the path registered with addEndpoint.
- **Using /stomp as the destination for sending messages:** /stomp is the transport endpoint; SEND needs a destination such as /app/chat.send.
- **Forgetting the context path:** the server runs under /messaging, so the external URL must include that prefix.
- **Enabling SockJS on the server while the client uses the wrong factory type:** a SockJS client needs a webSocketFactory that creates SockJS from the base endpoint URL.
- **Manually appending /websocket to the SockJS URL:** the SockJS client constructs the transport path itself.
- **Configuring allowed origins with a URL that includes a path:** an Origin consists only of scheme, host, and port.
- **Assuming allowed origins is authentication:** Origin is only a browser control layer; authentication and authorization are still required.
- **Not using wss when the page runs on HTTPS:** the browser may block mixed content.
- **Subscribing only once when creating the client:** after a reconnect, subscriptions need to be recreated in onConnect.
- **Using /topic or /queue prefixes without checking the external broker:** these prefixes are conventions of the simple broker; an external broker may have different destination syntax.
- **Assuming a successful WebSocket connection means messages are already being routed:** you need to check STOMP frames and the broker/controller flow.

## 16. Deployment checklist

- [ ] Added spring-messaging and spring-websocket.
- [ ] Enabled @EnableWebSocketMessageBroker.
- [ ] Registered the endpoint path with registerStompEndpoints.
- [ ] Determined the full URL including scheme, host, port, context path, and endpoint path.
- [ ] Distinguished the endpoint path from /app, /topic, and /queue.
- [ ] Client uses ws/wss or a SockJS factory matching the server configuration.
- [ ] If using SockJS, the server calls withSockJS and the client uses the base URL.
- [ ] Configured allowed origins for frontends on different origins.
- [ ] Enabled authentication and authorization for handshake/STOMP messages.
- [ ] Handled the CSRF token if required by Spring Security.
- [ ] Reverse proxy forwards WebSocket Upgrade with appropriate timeouts.
- [ ] Client resubscribes after reconnect and calls deactivate when finished.
- [ ] Tested CONNECT, SUBSCRIBE, SEND, MESSAGE, reconnect, and rejected origins.

## 17. References

- [Spring Framework 7.0.10 — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework 7.0.10 — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework 7.0.10 — SockJS Fallback](https://docs.spring.io/spring-framework/reference/web/websocket/fallback.html)
- [Spring Framework 7.0.10 — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework 7.0.10 — STOMP Overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Security 7 — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [STOMP.js — JavaScript/TypeScript STOMP client](https://github.com/stomp-js/stompjs)
