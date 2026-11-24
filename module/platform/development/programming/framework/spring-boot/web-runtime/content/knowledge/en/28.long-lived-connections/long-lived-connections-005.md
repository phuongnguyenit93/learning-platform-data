# Configuring WebSocket in a Servlet Application

**Module:** Spring Boot - web-runtime  
**Parent topic:** Long-lived connections

## 1. Problem and Learning Objectives

A Servlet-based Spring Boot application already has a request–response REST API returning JSON, but now needs to support near-real-time order status screens, chat, or dashboards. The client must receive data **as soon as the server emits an event** and be able to send messages back without opening a new HTTP request for each event.

**WebSocket** is a full-duplex protocol (RFC 6455), initiated through an HTTP handshake and then maintaining a bidirectional exchange channel over a single connection. With the Spring Boot Servlet stack, you can use the **Spring Framework WebSocket API** to map a URL such as **/ws/echo** to a **WebSocketHandler**, or use a higher-level messaging layer like **STOMP over WebSocket**.

This lesson focuses on **configuring WebSocket in a Servlet application (Spring MVC, embedded Tomcat/Jetty/Undertow)**: dependencies, handler configuration, handshake, allowed origins, server limits, connection lifecycle, security, proxies, deployment, and testing. It is not a guide to the WebFlux reactive stack.

After this lesson, you will be able to:

1. Explain why the initial request uses HTTP while subsequent messages are no longer regular **@GetMapping** requests.
2. Know when to use **spring-boot-starter-websocket**, **@EnableWebSocket**, **WebSocketConfigurer**, and **TextWebSocketHandler**.
3. Run a Java 17+ example echoing over **ws://localhost:8080/ws/echo** with a test web page and a Java standard-library client.
4. Configure **ServletServerContainerFactoryBean** to tune the Jakarta WebSocket container's buffers and idle timeout, alongside message-level validation.
5. Identify requirements for **Origin**, **ws/wss**, handshake authentication, and message-level authorization.
6. Set up reverse proxy routing, monitor connection lifecycles, and implement reconnect/heartbeats and resource limits for production.
7. Distinguish **raw WebSocket**, **STOMP**, **SockJS**, **SSE**, and **WebFlux** to choose the right tool for your scope.

## 2. How Does WebSocket Differ from HTTP Request–Response?

In traditional REST, the client sends each request and the server returns one response:

~~~text
Browser                              Spring MVC
   | GET /api/orders/42                  |
   |------------------------------------>|
   |<------------------- 200 JSON -------|
   |
   | GET /api/orders/42 (poll again)     |
   |------------------------------------>|
   |<------------------- 200 JSON -------|
~~~

With WebSocket, the client performs an HTTP handshake once, after which both sides can proactively send messages:

~~~text
Browser                               Servlet container + WebSocketHandler
   | GET /ws/echo HTTP/1.1                 |
   | Upgrade: websocket                   |
   |------------------------------------->|
   |<---------- 101 Switching Protocols --|
   |                                      |
   |--- WebSocket TEXT: "ping" ---------->|
   |<-- WebSocket TEXT: "echo:ping" -------|
   |                                      |
   |<-- WebSocket TEXT: server event ------|
   |--- WebSocket CLOSE ----------------->|
~~~

After **101 Switching Protocols**, the same TCP connection is used to exchange **WebSocket frames** (text, binary, ping, pong, close), rather than each message creating an HTTP GET or POST. WebSocket guarantees message ordering on the connection, yet defines no semantics such as "send to chat room" or "identify which account": **the application must define its own message protocol or choose STOMP**.

### When Is WebSocket Worth Using?

| Requirement | WebSocket | Potentially Simpler Alternative |
| --- | --- | --- |
| Continuous, high-frequency bidirectional near-real-time interaction | Suitable | — |
| Server only pushes notifications one way | Usable | **Server-Sent Events (SSE)** may suffice |
| Checking status once every few minutes | Likely unnecessary complexity | HTTP polling + caching |
| Standard CRUD APIs | Not the default choice | REST request–response |
| Multi-user chat, pub/sub, destination-based routing | WebSocket with **STOMP** or another messaging layer | Broker/message infrastructure |
| Clients or proxies that do not support Upgrade/long connections | May not work directly | HTTP streaming, long polling, or SockJS fallback |

**Do not equate WebSocket with HTTP/2 multiplexing.** HTTP/2 optimizes multiple request/response exchanges as streams on one connection; WebSocket is a bidirectional message channel with its own framing. In standard HTTP/1.1 flows, WebSocket starts with Upgrade; **RFC 8441 extended CONNECT** exists for WebSocket over HTTP/2, yet it requires both ends and all hops to support it, so do not assume an embedded Servlet app or proxy always uses that mode.

## 3. The HTTP Handshake: Switching from a Servlet Request to WebSocket

A typical WebSocket handshake over HTTP/1.1 looks like this:

~~~http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: http://localhost:8080
~~~

When accepting, the server responds with:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
~~~

The **Sec-WebSocket-Key/Sec-WebSocket-Accept** values in the example are a protocol sample pair, not passwords or auth tokens. After the 101 response, client and server exchange WebSocket frames.

**Key points to distinguish:**

- **Upgrade: websocket** requests a protocol switch on HTTP/1.1; the **Connection: Upgrade** header is hop-by-hop and may need explicit forwarding by proxies.
- **Sec-WebSocket-Version: 13** is the standard WebSocket protocol version per RFC 6455.
- **Sec-WebSocket-Key/Accept** verifies WebSocket handshake consistency—it **does not authenticate the user's identity**.
- **Origin** from the browser indicates the origin of the page initiating the socket; it is normally **http(s)://...**, not **ws://...**. The server must validate allowed origins itself.
- **101 Switching Protocols** is not an HTTP 200 with a JSON body. After the handshake, the application works with **WebSocketSession** and **WebSocketMessage**.
- If the handshake is invalid or forbidden, the server may return **400/403/404/401**, another HTTP error, or close the connection depending on the layer. Browsers usually report only a generic WebSocket connection failure; inspect Network/WS, access logs, and proxy logs for the cause.

On **HTTPS**, browsers normally connect via **wss://**, meaning WebSocket over TLS. With a **ws://** URL, that hop is not encrypted by TLS. You do not secure a public WebSocket connection merely by writing `wss` in the frontend if the server or proxy lacks valid TLS.

## 4. What Do the Servlet Container and Spring Framework Do?

In a Spring Boot Servlet application:

~~~text
Browser or Java WebSocket client
      |
      v
HTTP connector (Tomcat/Jetty/Undertow)
      |
      v
Servlet filters / security for HTTP handshake
      |
      v
Spring WebSocket handshake mapping
      |
      v
RequestUpgradeStrategy + Jakarta WebSocket ServerContainer
      |
      v
WebSocketHandler / WebSocketSession
      |
      +--> afterConnectionEstablished
      +--> handleTextMessage / handleBinaryMessage
      +--> handleTransportError
      +--> afterConnectionClosed
~~~

**Spring Boot** provides WebSocket auto-configuration for supported embedded Servlet containers, with **Tomcat** as the default when using `spring-boot-starter-web`. **spring-boot-starter-websocket** brings in the dependencies needed for Spring's WebSocket features on MVC. The container handles connections and upgrades, while Spring WebSocket provides **WebSocketHandler**, URL mapping, handshake integration, and a convenient programming model.

**@EnableWebSocket** enables programmatic WebSocket configuration in Spring MVC. **WebSocketConfigurer#registerWebSocketHandlers** maps handshake URLs to handlers. You do not need to register a custom Servlet manually or write **@GetMapping("/ws/echo")** to return 101 by hand.

API options:

| Approach | Library/API | Meaning |
| --- | --- | --- |
| Raw Spring WebSocket | **@EnableWebSocket**, **WebSocketConfigurer**, **WebSocketHandler/TextWebSocketHandler** | Custom message format, events, and routing. |
| STOMP messaging | **@EnableWebSocketMessageBroker**, **WebSocketMessageBrokerConfigurer**, **@MessageMapping** | Publish/subscribe routing using STOMP destinations. |
| Direct Jakarta WebSocket | **@ServerEndpoint**, Jakarta WebSocket API | A different endpoint registration path, not identical to Spring WebSocketHandler. |
| Reactive WebSocket | **WebFlux WebSocketHandler**, **HandlerMapping**, reactive **WebSocketService/Session** | For the WebFlux/Reactive stack. |

**Do not mix raw @EnableWebSocket configuration with a STOMP broker as if the two APIs were one.** Pick one style based on your needs, or map **two separate endpoints** if the system requires both.

## 5. Dependencies and Spring Boot 3.x Project

The demo uses **Spring Boot 3.3.13, Java 17+, and Maven**. That is a stable release in the 3.3 line for example compatibility; new projects should pick a still-maintained Spring Boot release with current security patches for their deployment environment.

Structure:

~~~text
servlet-websocket-demo/
  pom.xml
  src/main/
    java/com/example/wsdemo/
      ServletWebSocketDemoApplication.java
    resources/
      application.properties
      static/index.html
  WebSocketProbe.java
~~~

Complete **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>servlet-websocket-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**spring-boot-starter-websocket** provides Spring WebSocket/Spring Messaging modules and embedded server integration. We explicitly include **spring-boot-starter-web** in the POM to make clear this application runs **Servlet Spring MVC**. Do not add **spring-boot-starter-webflux** in this demo, and do not add Reactor Netty classes just to receive WebSocket messages.

**application.properties** at **src/main/resources/application.properties**:

~~~properties
server.port=8080
spring.application.name=servlet-websocket-demo

# There is no global server.websocket.enabled=true property for all endpoints;
# handlers are registered via @EnableWebSocket + WebSocketConfigurer.
~~~

**Key point to remember:** Spring Boot enables WebSocket container support via auto-configuration, yet you still must **register endpoints and handlers**. There is no single property that automatically exposes `/ws/echo` when enabled.

## 6. Runnable Java 17+ Example: WebSocket Echo Endpoint

Create **src/main/java/com/example/wsdemo/ServletWebSocketDemoApplication.java**:

~~~java
package com.example.wsdemo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import org.springframework.web.socket.server.standard.ServletServerContainerFactoryBean;

@SpringBootApplication
public class ServletWebSocketDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletWebSocketDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebSocket
class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoWebSocketHandler handler;

    WebSocketConfiguration(EchoWebSocketHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/echo")
                .setAllowedOrigins(
                        "http://localhost:8080",
                        "http://localhost:5173");
    }

    @Bean
    ServletServerContainerFactoryBean webSocketContainer() {
        ServletServerContainerFactoryBean container =
                new ServletServerContainerFactoryBean();
        container.setMaxTextMessageBufferSize(8 * 1024);
        container.setMaxBinaryMessageBufferSize(8 * 1024);
        container.setMaxSessionIdleTimeout(60_000L);
        return container;
    }
}

@Component
class EchoWebSocketHandler extends TextWebSocketHandler {

    private static final Logger logger =
            LoggerFactory.getLogger(EchoWebSocketHandler.class);

    private static final int MAX_APP_TEXT_BYTES = 1024;

    @Override
    public void afterConnectionEstablished(WebSocketSession session)
            throws IOException {
        logger.info("WebSocket opened: {}", session.getId());
        session.sendMessage(new TextMessage("ready"));
    }

    @Override
    protected void handleTextMessage(
            WebSocketSession session, TextMessage message)
            throws IOException {

        String payload = message.getPayload();
        int bytes = payload.getBytes(StandardCharsets.UTF_8).length;

        if (bytes > MAX_APP_TEXT_BYTES) {
            session.close(CloseStatus.TOO_BIG_TO_PROCESS);
            return;
        }

        session.sendMessage(new TextMessage("echo:" + payload));
    }

    @Override
    public void handleTransportError(
            WebSocketSession session, Throwable exception)
            throws Exception {
        logger.warn("WebSocket transport error: {}",
                exception.toString());
        if (session.isOpen()) {
            session.close(CloseStatus.SERVER_ERROR);
        }
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session, CloseStatus status) {
        logger.info("WebSocket closed: id={}, code={}",
                session.getId(), status.getCode());
    }
}
~~~

### 6.1. Why Does This Code Run?

- Only **ServletWebSocketDemoApplication** is a public class, matching the filename. The other two classes are package-private in the same package and picked up by component scanning.
- **@EnableWebSocket** activates Spring MVC's WebSocket configuration.
- **WebSocketConfiguration** receives the **EchoWebSocketHandler** bean via constructor injection; **@Component** lets Spring instantiate the handler with dependency injection.
- **registry.addHandler(handler, "/ws/echo")** creates the handshake endpoint.
- **setAllowedOrigins** permits browser WebSocket connections only from **http://localhost:8080** or the dev frontend **http://localhost:5173**. This is a local test allowlist; replace it with valid HTTPS domains in production.
- **ServletServerContainerFactoryBean** configures the server container on embedded Tomcat/Jakarta WebSocket: 8 KiB text/binary message buffers and a 60,000 ms idle timeout. These values are **demo** settings, not universal optimal defaults for every application.
- **TextWebSocketHandler** handles text messages; binary messages are unsupported in this demo and handled by Spring according to the base class semantics.
- Once connected, the server sends **ready**. When the client sends **ping**, the server replies **echo:ping**.
- The application-level text limit is **1,024 UTF-8 bytes**, distinct from the container's 8 KiB buffer. Exceeding it causes the server to close with status **1009 (TOO_BIG_TO_PROCESS)**. In some cases, the container rejects oversized payloads before the handler sees them if they exceed the container limit.
- The handler sends a single direct reply per received message; there are no multiple async producers pushing into one session. For production broadcasts or fan-out, coordinate **concurrent writes**, buffers, and slow-consumer controls.
- **Logger** records only session IDs and close codes, never payloads, cookies, or tokens. Production logs must likewise avoid recording sensitive data or tokens.

### 6.2. Java API Classes to Understand

**WebSocketHandler** is the core interface whose callbacks are invoked by Spring/the container across the connection lifecycle. **TextWebSocketHandler** is a convenient base class when only text is needed.

| Callback/Method | When Does It Occur? | What Is It Used For? |
| --- | --- | --- |
| **afterConnectionEstablished(WebSocketSession)** | After handshake succeeds and WebSocket session is created | Send initial event, register connection, initialize ephemeral state. |
| **handleTextMessage(session, TextMessage)** | When a text message arrives | Validate message and process command/event. |
| **handleBinaryMessage(...)** | When a binary message arrives, if handler supports it | Use **BinaryWebSocketHandler** or implement as needed. |
| **handleTransportError(...)** | On transport failure | Log safely, close session, run cleanup. |
| **afterConnectionClosed(session, CloseStatus)** | When the connection closes | Release connection-specific resources and registry entries. |
| **session.sendMessage(new TextMessage(...))** | When sending a message | Write a WebSocket text message on the session. |
| **session.close(CloseStatus.XXX)** | When terminating the connection | Send a close frame when possible. |

Closure callbacks can fire due to client-initiated close, server timeout, proxy closure, or network errors. On abrupt network loss, the application cannot guarantee a clean close handshake; ensure timeout/lifecycle cleanup is resilient.

**WebSocketSession is not HttpSession**. WebSocketSession represents an upgraded connection, whereas HttpSession holds server-side HTTP state bound to a session cookie. Spring can transfer authentication info or copy attributes via **HandshakeInterceptor**, yet the two objects have distinct lifecycles and meanings.

## 7. Browser Page to Test the Endpoint

Create **src/main/resources/static/index.html**. Spring Boot Servlet serves this static file at **http://localhost:8080/** when default static resource handling is unchanged.

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Servlet WebSocket Echo</title>
</head>
<body>
  <h1>WebSocket Echo</h1>
  <input id="message" value="ping" aria-label="Message">
  <button id="send" type="button">Send</button>
  <button id="disconnect" type="button">Close</button>
  <pre id="log" aria-live="polite"></pre>

  <script>
    const input = document.querySelector("#message");
    const logArea = document.querySelector("#log");
    const append = (value) => {
      logArea.textContent += value + "\n";
    };

    const scheme = location.protocol === "https:" ? "wss://" : "ws://";
    const socketUrl = scheme + location.host + "/ws/echo";
    const socket = new WebSocket(socketUrl);

    socket.addEventListener("open", () => append("open"));
    socket.addEventListener("message", (event) =>
      append("received: " + event.data));
    socket.addEventListener("error", () => append("transport error"));
    socket.addEventListener("close", (event) =>
      append("closed: " + event.code));

    document.querySelector("#send").addEventListener("click", () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(input.value);
      } else {
        append("not open");
      }
    });

    document.querySelector("#disconnect").addEventListener("click", () => {
      socket.close(1000, "done");
    });
  </script>
</body>
</html>
~~~

After opening the page, the log may display:

~~~text
open
received: ready
received: echo:ping
~~~

**open** and **received: ready** can arrive close together; connection event ordering is preserved, while exact UI paint timing depends on the browser. Click **Send** with value `ping` to receive `echo:ping`; clicking **Close** yields a close code, typically **1000** when the close handshake completes cleanly.

**No fetch POST/GET calls are needed per message.** The browser **WebSocket API** exposes **send**, **message**, **open**, **close**, and **error**. Selecting ws/wss via **location.protocol** lets the page transition smoothly from local HTTP to production HTTPS (assuming the proxy exposes the WebSocket endpoint via wss).

**Cross-origin warning:** if the HTML is served from another address such as **http://localhost:3000**, that origin **is not in the demo allowlist**. Do not change allowedOrigins to **"*"** to silence an unexplained error; add the genuinely trusted origin, or run the frontend on 5173 as configured.

## 8. Running the Application and Testing with the Java 17 Standard Library

### 8.1. Build and Start

Inside **servlet-websocket-demo**:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

Keep the server running in the first terminal. If port 8080 is occupied, change `server.port` and visit the matching URL; in that case also update **allowedOrigins** for the new origin.

### 8.2. Java WebSocket Client Without External Libraries

Java 17 includes **java.net.http.HttpClient** and **java.net.http.WebSocket**. Create **WebSocketProbe.java** at the project root (outside `src/main/java`):

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public class WebSocketProbe {
    public static void main(String[] args) throws Exception {
        CompletableFuture<String> echo = new CompletableFuture<>();

        WebSocket.Listener listener = new WebSocket.Listener() {
            private final StringBuilder parts = new StringBuilder();

            @Override
            public void onOpen(WebSocket socket) {
                socket.request(1);
            }

            @Override
            public CompletionStage<?> onText(
                    WebSocket socket, CharSequence text, boolean last) {
                parts.append(text);
                if (last) {
                    String message = parts.toString();
                    parts.setLength(0);
                    if (message.startsWith("echo:")) {
                        echo.complete(message);
                    }
                }
                socket.request(1);
                return CompletableFuture.completedFuture(null);
            }

            @Override
            public void onError(WebSocket socket, Throwable error) {
                echo.completeExceptionally(error);
            }
        };

        WebSocket socket = HttpClient.newHttpClient()
                .newWebSocketBuilder()
                .buildAsync(
                        URI.create("ws://localhost:8080/ws/echo"),
                        listener)
                .join();

        socket.sendText("ping", true).join();
        System.out.println(echo.get(5, TimeUnit.SECONDS));
        socket.sendClose(WebSocket.NORMAL_CLOSURE, "done").join();
    }
}
~~~

Compile/run in a second terminal:

~~~bash
javac WebSocketProbe.java
java WebSocketProbe
~~~

**Exact expected stdout** while the demo server is running with no proxy:

~~~text
echo:ping
~~~

**Why is this test meaningful?**

- No need for **wscat**, Node.js, or third-party tools. The Java standard-library client performs the handshake and WebSocket framing itself.
- **onOpen** supplies demand via **request(1)** so the listener receives messages.
- **onText** reassembles fragments until **last=true**; it ignores the initial **ready** message and completes the future only upon receiving **echo:**.
- **sendText("ping", true)** sends a complete text message.
- **CompletableFuture.get(5, SECONDS)** bounds the test wait so failures surface clearly; this is not a production service global timeout.
- A Java client is not a browser and **may omit Origin**. A passing Java client test does not prove browsers from disallowed origins will be accepted.
- **sendClose** sends a standard close frame. In failing network conditions, the close handshake may not complete as cleanly as in this happy-path test.

### 8.3. Do Not Test Raw WebSocket Only with a curl GET

Sending a plain HTTP GET to **/ws/echo**:

~~~bash
curl -i http://localhost:8080/ws/echo
~~~

does not perform a valid WebSocket handshake because required Upgrade/Sec-WebSocket-* headers are absent. You will likely receive **400** or another error response. Do not conclude the endpoint is broken just because a curl GET doesn't return JSON.

You can use **curl** to inspect HTTP handshake headers partially, yet after **101** it is not the most convenient tool for reading/writing WebSocket frames in a demo. Browser DevTools WebSocket frames or **WebSocketProbe** above is far more reliable.

## 9. Allowed Origins: Checking Page Origin, Not User Authentication

The demo registers:

~~~java
registry.addHandler(handler, "/ws/echo")
        .setAllowedOrigins(
                "http://localhost:8080",
                "http://localhost:5173");
~~~

**Origin** in a browser WebSocket handshake identifies the web page initiating the connection. When a page at **https://app.example.test** opens **wss://api.example.test/ws/echo**, Origin is normally **https://app.example.test**, not **wss://api.example.test**.

By default, Spring WebSocket **restricts cross-origin WebSocket/SockJS requests** (same-origin when nothing extra is permitted). If your frontend runs on another origin, add that exact origin. The API also offers **setAllowedOriginPatterns(...)** for controlled patterns; never blindly echo back client Origin headers.

**Browser WebSocket does not use CORS preflight OPTIONS like fetch/xhr.** The browser sends `Origin` in the handshake, and Spring checks allowed origins via the WebSocket policy. Do not assume **@CrossOrigin** on a REST controller or **CorsFilter** automatically allows a WebSocket endpoint. With SockJS HTTP fallbacks, SockJS HTTP transports have their own CORS requirements handled by Spring/SockJS configuration.

**Origin does not prove identity.** Non-browser clients can omit or spoof `Origin`. Therefore `allowedOrigins` guards against many **cross-site WebSocket hijacking** scenarios in browsers, **without replacing authentication, authorization, CSRF/CSWSH defense-in-depth, or message-level validation**.

### Why Not Use setAllowedOrigins("*")?

An endpoint relying on session cookies can be opened by a browser from an attacker's page if the app permits every origin; after the handshake, the attacker could send/receive messages under the user's active credentials if unprotected. Use a strict allowlist, proper cookie attributes, handshake authentication, permission checks, and CSWSH-resistant tokens as dictated by your threat model.

For a truly public anonymous chat service, a wildcard might be a deliberate product choice, yet it still requires rate limits, abuse controls, and no reliance on sensitive cookies; it is never a safe default for authenticated apps.

## 10. Authentication and Authorization over WebSocket in Servlet

**The HTTP handshake still passes through the Servlet filter chain and can be protected by Spring Security.** If the application uses cookie/session authentication, the browser sends applicable cookies during the handshake; Spring Security resolves the Principal on the HTTP request, and Spring WebSocket attaches that identity to **WebSocketSession.getPrincipal()**.

Model:

~~~text
Browser + session cookie
    |
    v
GET /ws/notifications Upgrade: websocket
    |
    v
Spring Security Servlet filters
    |
    +--> authenticated HTTP principal?
    |          |
    |          +--> No: reject handshake
    |          +--> Yes: proceed
    |
    v
WebSocket handshake -> WebSocketSession Principal
    |
    v
Each incoming message:
    handler/message-security checks action and resource scope
~~~

**The demo in section 6 intentionally omits Spring Security** to focus on WebSocket configuration and allow anonymous echo. Never carry that anonymous endpoint as-is into an app handling user accounts and sensitive data.

### 10.1. Protecting the Handshake with SecurityFilterChain

This is **an alternative configuration snippet for projects including spring-boot-starter-security**, not part of the public echo demo in section 6. It illustrates handshake route protection:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/ws/notifications").authenticated()
                    .anyRequest().permitAll())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

Corresponding imports belong to **org.springframework.security.web.SecurityFilterChain**, **org.springframework.security.config.annotation.web.builders.HttpSecurity**, **org.springframework.security.config.Customizer**, and **org.springframework.context.annotation.Bean**. A working login/session mechanism must also be configured; this snippet is not a standalone class.

After 101, Spring Security servlet filters **do not re-run for each WebSocket text frame** as they do for new HTTP requests. Therefore **the handler or messaging layer must authorize each command/message/subscription** where required. Never infer from "logged in at connect" that the user is authorized to act on every order ID inside a payload.

### 10.2. Principal and HttpSessionHandshakeInterceptor

You can attach Spring's **HttpSessionHandshakeInterceptor**:

~~~java
registry.addHandler(handler, "/ws/notifications")
        .addInterceptors(new HttpSessionHandshakeInterceptor())
        .setAllowedOrigins("https://app.example.test");
~~~

This is an **alternative configuration snippet inside WebSocketConfigurer** for apps already using HTTP sessions; do not copy it into the echo demo unnecessarily. **HttpSessionHandshakeInterceptor** copies eligible attributes from the HTTP session into the `WebSocketSession` attribute map, making context available after the handshake.

**Distinction:** copying HttpSession attributes **does not re-authenticate every message** and does not guarantee WebSocket session data stays continuously synchronized with the HTTP session. Avoid copying unnecessary tokens or PII; never trust roles sent in client messages. For `Principal`, prefer authentication populated by Spring Security.

### 10.3. Browsers Cannot Set Arbitrary Authorization Headers in the WebSocket Constructor

The standard browser WebSocket API accepts only **URL** and optional **subprotocols**; it does not let JavaScript attach an arbitrary **Authorization: Bearer ...** header like `fetch`. Authentication must be designed specifically, such as:

- **Session cookies** for same-site web apps, paired with allowed origins, proper `SameSite`/`Secure`/`HttpOnly`, and CSWSH protection.
- **Short-lived, single-use connection tickets** issued by the backend over an authenticated HTTPS call with tight TTL, audience, and binding; use a secure handshake mechanism to transmit and verify the ticket.
- **STOMP CONNECT headers** when using STOMP messaging, paired with Spring Security messaging/channel interceptors as appropriate.
- **Native clients** may have library APIs to attach headers flexibly, but do not assume browsers share that capability.

Never place long-lived access tokens in query strings like **/ws?token=...** without accounting for URL/access logs, analytics, browser history, referer exposure, rotation/replay, and timeouts. Never abuse **Sec-WebSocket-Protocol** as an arbitrary token carrier without compatible subprotocol and auth design, as doing so risks leaks or breaking protocol negotiation.

## 11. Configuring the Jakarta Servlet WebSocket Server Container

In the demo, the bean:

~~~java
@Bean
ServletServerContainerFactoryBean webSocketContainer() {
    ServletServerContainerFactoryBean container =
            new ServletServerContainerFactoryBean();
    container.setMaxTextMessageBufferSize(8 * 1024);
    container.setMaxBinaryMessageBufferSize(8 * 1024);
    container.setMaxSessionIdleTimeout(60_000L);
    return container;
}
~~~

**ServletServerContainerFactoryBean** configures the **Jakarta WebSocket ServerContainer** in `ServletContext`. This is Spring Framework's standard mechanism for Jakarta WebSocket servers; alternative servers such as Jetty may also use specific upgrade strategies and native container settings depending on version.

| Setting | Meaning | Caveats |
| --- | --- | --- |
| **setMaxTextMessageBufferSize(8192)** | Container text message buffer size/limit | Do not treat as the sole business limit for all stream shapes; the handler should validate actual payloads. |
| **setMaxBinaryMessageBufferSize(8192)** | Buffer for binary payloads | The demo `TextWebSocketHandler` does not process binary messages; setting a buffer does not imply binary uploads are supported. |
| **setMaxSessionIdleTimeout(60000L)** | Container idle timeout in milliseconds | Depends on connection activity and implementation; does not replace proxy idle timeouts. |
| **setAsyncSendTimeout(...)** | Timeout for asynchronous sends where supported by container | Does not replace HTTP request timeouts; verify per API/transport. |

**Distinguish the two limit tiers:** 8 KiB at the container is a transport/parser/buffer setting. 1 KiB in the handler is a business limit on text payloads. If a client sends something huge, the container may close before the handler sees it; if it sends 2 KiB, the handler receives it and closes with **1009**.

Container settings **do not automatically cap total connections**, requests/sec, total JVM buffer bytes, or client read rates. Enforce those at the proxy/container and in application capacity planning.

### Buffering and Memory Under Many Connections

If each connection holds several KiB or more in buffers and metadata, tens of thousands of concurrent connections incur substantial memory, file descriptor, socket, and heartbeat costs. A WebSocket connection **does not hold a Servlet thread blocked for its entire lifetime**, yet dispatching callbacks and blocking work inside handlers still consumes thread and CPU resources.

Never sleep a thread waiting for messages, and never run infinite loops inside **handleTextMessage**. Avoid slow blocking database calls directly in callbacks under high throughput/concurrency; offload work to properly bounded workers/brokers with deadlines, timeouts, and backpressure/queue budgets.

## 12. Connection Lifecycle, Heartbeats, and Reconnection

WebSocket is a **long-lived connection**, not an immortal one. It can drop due to:

- Browser closing the tab or losing network connectivity.
- Proxy/load balancer **idle/read timeouts**.
- Server restarts, rolling deployments, or node replacement.
- Firewalls/NATs dropping inactive connections.
- Rejected sessions or changed security policies.
- Oversized payloads, invalid frames, protocol errors, or slow consumers.

Key lifecycle events:

~~~text
CONNECTING -> OPEN -> MESSAGE(s) -> CLOSING -> CLOSED
                  |
                  +---- error / timeout / network failure ----> CLOSED
~~~

**Browser WebSocket readyState** is a local state machine: **CONNECTING (0)**, **OPEN (1)**, **CLOSING (2)**, **CLOSED (3)**. The browser API exposes **close(code, reason)** and a **close** callback; the backend has **afterConnectionEstablished/afterConnectionClosed**.

### Ping/Pong and Application-Layer Heartbeats

RFC 6455 defines **Ping** and **Pong** control frames. The browser WebSocket API does not expose a method to send arbitrary Ping frames like application messages. Certain servlet containers, WebSocket clients, and STOMP brokers have built-in ping/heartbeat mechanisms.

An application can also define an **application heartbeat message** (such as text **heartbeat** or JSON type **ping**) when both sides agree on the schema. **An application heartbeat is not a Ping control frame.** Use heartbeats to detect dead connections, choosing a frequency balanced against proxy idle timeouts and real concurrency costs.

Do not turn on 1-second pings for hundreds of thousands of clients just to feel "always online"; measure bandwidth, CPU, and resource impact. The server may close idle sessions after inactivity, documenting the idle policy clearly for clients.

### Reconnect

In production, clients should implement **exponential backoff + jitter**, cap retry attempts/duration, verify the auth session is still valid, and resubscribe/recover state on reconnect. When a server emits continuous events, a dropped connection can miss events during the gap; **WebSocket does not provide built-in replay, acks, or durable delivery**. If zero loss is required, add event IDs, cursors, storage/brokers, or protocol-level ack/replay.

**Do not retry immediately in a tight loop** during backend deployments or auth rejections, as that triggers a thundering herd. When close codes indicate policy violations or auth failures, retry behavior must differ from transient network errors.

## 13. Sending on the Same WebSocketSession from Multiple Threads: A Production Trap

WebSocket transports enforce rules around **concurrent sends**. The demo calls `sendMessage` only inside its message/open callbacks, keeping things simple. However, if a system broadcasts from multiple schedulers or event listeners simultaneously into one session, two threads risk sending concurrently; the underlying session may not support concurrent sends.

Spring provides **ConcurrentWebSocketSessionDecorator** to serialize sends and enforce **sendTimeLimit/bufferSizeLimit**, helping catch slow consumers. Illustrative example:

~~~java
WebSocketSession safeSession =
        new ConcurrentWebSocketSessionDecorator(
                rawSession,
                10_000,       // sendTimeLimit milliseconds
                128 * 1024);  // bufferSizeLimit bytes
~~~

Imports: **org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator** and **org.springframework.web.socket.WebSocketSession**. This snippet belongs **inside a connection registry/service** managing **rawSession**, not standalone runnable code.

**Important:** wrap `rawSession` once per connection upon registering it; every producer must **use that same decorator instance**. Wrapping a fresh decorator on every send defeats serialization. Clean up the registry on close, limit connections, and watch buffer pressure. A decorator does not give slow consumers infinite capacity; exceeding limits requires closing, dropping, or applying backpressure per policy.

For very large payloads or fan-out across tens of thousands of subscribers, a STOMP broker, event backbone, or dedicated pub/sub architecture fits better than broadcasting from a hand-rolled `ConcurrentHashMap` lacking lifecycle/retention controls.

## 14. Reverse Proxies, TLS, and Upgrade Headers

In production, requests normally flow through an ingress/proxy:

~~~text
Browser -- wss://api.example.test/ws/echo -->
          Nginx / CDN / Ingress [TLS termination]
             |
             +-- HTTP/1.1 Upgrade websocket -->
                   Spring Boot :8080 /ws/echo
~~~

If the proxy fails to forward **Upgrade** and **Connection** headers over HTTP/1.1, you may get 400/404/502 or timeouts instead of 101. The web server must keep the connection open after the handshake rather than treating it like a short HTTP request.

Example Nginx snippet for **an HTTP/1.1 upstream to Spring Boot**, within an Nginx setup that already configures TLS/public server blocks:

~~~nginx
# Place in Nginx's http context, NOT inside location.
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# Place location inside the server block serving the public domain.
location /ws/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $host;
    proxy_read_timeout 3600s;
}
~~~

This sample shows how to forward WebSocket upgrades over HTTP/1.1; it **is not a full nginx.conf** and omits certificates, upstream load balancing, rate limits, and logging policies. **map** belongs in the **http context**; **location** belongs in the **server block**. Never expose this location publicly without authentication when handling sensitive data.

**Key points to remember:**

- Browser URLs on HTTPS pages should use **wss://...** to avoid mixed content.
- TLS termination at the proxy encrypts only the browser–proxy hop; if proxy–Spring Boot uses **http://**, that hop is cleartext. Across untrusted networks, use TLS/mTLS to the origin.
- HTTP/2 on browser–proxy **does not guarantee h2 WebSocket to Spring**. Proxies commonly convert to **HTTP/1.1 Upgrade** to the backend; RFC 8441 extended CONNECT applies only when all hops support it.
- Proxies/ingresses can cap idle connections, total concurrent connections, or request header sizes independently of the app. **Server container idle timeout** and **proxy_read_timeout** must be coordinated together.
- Across multiple pods/replicas, each WebSocket connection stays pinned to one node for its lifetime. **WebSocket does not automatically distribute messages across nodes**; cluster-wide broadcast requires a broker/event bus or dedicated routing/state strategy.
- The **Origin** header still represents the browser origin. Do not change `allowedOrigins` to an internal proxy hostname; configure the public frontend domain.
- Only trust **Forwarded/X-Forwarded-Proto/X-Forwarded-Host** from authenticated/trusted proxies. Spoofed headers can corrupt schemes, URLs, and security checks.

## 15. Authentication and Protection Across Multiple Instances

Suppose there are two replicas:

~~~text
                       +--> Pod A: ws session #1, #2
Client --> Load Balancer
                       +--> Pod B: ws session #3, #4
~~~

Each client holds a connection to a single pod. If a service publishes an event only inside Pod A, clients on Pod B **do not receive it automatically**. Three main designs exist:

1. **Raw WebSocket + event bus:** each node keeps a local connection registry; domain events arrive via Redis Pub/Sub, Kafka, RabbitMQ, or similar; each node forwards to its local clients. Account for ordering, duplicates, and loss.
2. **STOMP + external broker relay:** use Spring Messaging/STOMP with a broker such as RabbitMQ/ActiveMQ for richer pub/sub features; distinguish broker relay from the simple in-memory broker.
3. **No cross-node live broadcast needed:** if sockets only update an account connected to its target node, use sticky/session routing or a backplane as needed while handling reconnects and failover.

**Do not assume sticky sessions alone solve cross-node event delivery.** Stickiness keeps a connection/request on one node, not message delivery across nodes. If Spring Security uses server-side session state, configure a shared session-store strategy so handshakes/reconnects work across pods.

During rolling deployments:

- Drain connections before stopping a node, or send a reconnect signal using an app-defined close code.
- Clients must reconnect with backoff and recover subscriptions/state.
- There is no way to keep an open socket alive across pod destruction; **graceful shutdown** reduces disruption but does not turn WebSocket into a durable channel.

## 16. Raw WebSocket vs. STOMP over WebSocket

The raw handler in the demo has an ultra-simple app contract: text in → **echo:** out. To add chat rooms, topic subscriptions, private recipients, or typed messages, you would have to invent message types, routing, authorization, and ordering rules yourself. **STOMP** is a frame-based messaging protocol layered over WebSocket, providing commands like **CONNECT, SEND, SUBSCRIBE, DISCONNECT** and destination headers.

Comparison:

| Criterion | Raw WebSocket | STOMP over WebSocket |
| --- | --- | --- |
| Spring configuration | **@EnableWebSocket + WebSocketConfigurer** | **@EnableWebSocketMessageBroker + WebSocketMessageBrokerConfigurer** |
| Business handling | **WebSocketHandler.handleTextMessage** | **@MessageMapping**, message channels |
| Payload and routing | Custom-designed | STOMP destinations, broker routes |
| Frontend client | Browser **new WebSocket(...)** | Usually **stompjs** or a STOMP client |
| Broadcast | Custom session registry/backplane | Built-in simple broker or external broker relay |
| Message security | Checked manually in handlers | Spring Security messaging authorization on inbound channels |
| SockJS fallback | Can add `.withSockJS` with compatible config | Commonly used on STOMP endpoints when fallback is needed |
| Cost/complexity | Low for simple cases, grows fast with pub/sub | Adds protocol abstraction and broker semantics |

### STOMP Configuration Is a Separate Option

An **illustrative example for a dedicated STOMP project**, not placed on the same **/ws/echo** path as the raw demo:

~~~java
@Configuration
@EnableWebSocketMessageBroker
class StompMessagingConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws-stomp")
                .setAllowedOrigins("https://app.example.test");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Imports belong to **org.springframework.context.annotation.Configuration**, **org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker**, **WebSocketMessageBrokerConfigurer**, **StompEndpointRegistry**, and **org.springframework.messaging.simp.config.MessageBrokerRegistry**. This is **a configuration class**, not a complete app because it still needs a Spring Boot main class and STOMP handlers.

- Clients open WebSocket connections to **/ws-stomp**.
- STOMP **SEND** frames to **/app/...** route to matching **@MessageMapping** methods.
- Subscriptions to **/topic/...** or **/queue/...** are served by the built-in simple broker per design.
- **enableSimpleBroker** is an in-memory broker useful for learning/local setups, not a clustered or durable messaging solution. Use a relay/external broker or backplane in distributed deployments.
- Adding **.withSockJS()** also requires the client to use a SockJS-compatible library; it does not magically turn a raw browser **new WebSocket** call into a SockJS client.

**STOMP security** has specific requirements: Spring Security can require a **CSRF token in STOMP CONNECT** to defend against cross-site WebSocket hijacking. Consult Spring Security messaging documentation for your version. Never disable CSRF globally just because a SockJS transport throws an error.

## 17. Servlet WebSocket vs. WebFlux WebSocket

In Spring Boot:

- **Servlet MVC**: **spring-boot-starter-websocket**, **@EnableWebSocket**, **WebSocketConfigurer**, **TextWebSocketHandler**, and Jakarta WebSocket container configured as in this demo.
- **Reactive WebFlux**: **spring-boot-starter-webflux**, WebFlux **WebSocketHandler**, reactive **WebSocketSession**, **Mono/Flux** types, **HandlerMapping**, and reactive runtime adapters.

Both stacks have classes named **WebSocketHandler/WebSocketSession**, yet their **packages and semantics differ**. In Servlet, handlers live in **org.springframework.web.socket**; in WebFlux, reactive APIs live in **org.springframework.web.reactive.socket**. Never import the wrong package and try to pass a reactive handler into MVC's **WebSocketHandlerRegistry**.

If a project includes both **spring-boot-starter-web** and **spring-boot-starter-webflux**, Spring Boot normally selects Servlet MVC via default auto-configuration; having Reactor in dependencies does not mean the WebSocket server runs on WebFlux.

## 18. Embedded Servlet Container vs. WAR on a Standalone Server

Spring Boot provides WebSocket auto-configuration for **embedded Tomcat, Jetty, and Undertow**. In an executable JAR demo, Boot manages the embedded servlet container and WebSocket support.

When packaging a **WAR** to deploy into a **standalone Servlet container**, Spring Boot relies on that container to supply the WebSocket runtime and container-level configuration. Ensure:

- The server supports the Jakarta WebSocket API matching your Spring Boot/Spring Framework version (Spring Boot 3 uses **jakarta.***, not **javax.***).
- Proper classpath and Servlet initialization for WAR deployment.
- Spring's handshake mappings register under the right context path.
- Reverse proxies or application servers do not block Upgrade.
- Buffers/idle timeouts are tuned via container-compatible APIs; **ServletServerContainerFactoryBean** works when the Jakarta WebSocket ServerContainer is available.

**Do not mix @ServerEndpoint and Spring WebSocketHandler arbitrarily.** When using Jakarta **@ServerEndpoint** directly, embedded runtimes often require endpoint registration (such as **ServerEndpointExporter** in appropriate Spring configs); in standalone WAR deployments, containers scan endpoints themselves and a duplicate exporter can cause errors. The raw Spring `WebSocketConfigurer` demo **does not require @ServerEndpoint or ServerEndpointExporter**.

Watch out for package migration: legacy code importing **javax.websocket** is not directly compatible with the Spring Boot 3/Jakarta Servlet stack simply by swapping dependencies.

## 19. Testing Real Behavior and Failure Cases

### 19.1. Checks to Run

1. Start the server, visit **/**, and confirm the browser receives HTML.
2. Confirm the browser opens a WebSocket to **ws://localhost:8080/ws/echo** with handshake **101**.
3. Inspect **ready** and **echo:ping** in DevTools **Network → WS → Messages/Frames**.
4. Send a payload >1,024 UTF-8 bytes and confirm the server closes per policy/size; the close code can be **1009** when the handler catches it before the container limit.
5. Run Java `WebSocketProbe` and confirm stdout prints **echo:ping**.
6. Serve a frontend from a non-allowlisted origin; the handshake should be rejected when the browser sends the disallowed `Origin`.
7. Connect through a public HTTPS/wss proxy; compare **101** at edge vs. origin and inspect Upgrade/Connection headers.
8. Drop network connectivity, restart the server, and verify close/error handling and reconnect logic.
9. Test buffer/idle timeouts and active connection counts under growing load.
10. For production security, test cookies/sessions, origin policies, per-resource read/write authorization, and session revocation/reconnect.

### 19.2. Spring Boot Integration Test with Random Port

With **spring-boot-starter-test** (if added to pom for CI), you can write a **@SpringBootTest(webEnvironment = RANDOM_PORT)** test using Java **HttpClient.newWebSocketBuilder()** to test real handshakes and frames on the embedded server. Do not rely solely on **MockMvc**, because mock MVC requests do not simulate full WebSocket frame lifecycles, browser Origin enforcement, container buffers, or proxies.

Outline adapted from `WebSocketProbe`:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class EchoWebSocketIntegrationTests {
    @LocalServerPort
    int port;

    // Use HttpClient.newWebSocketBuilder(), listener, and
    // CompletableFuture as in WebSocketProbe.
    // Connect to "ws://localhost:" + port + "/ws/echo".
    // Send text "ping" and assert response "echo:ping".
}
~~~

This is an **illustrative skeleton**, not a standalone compilable test. To make it runnable right away, move the listener/CompletableFuture logic from **WebSocketProbe** into a test method, add imports for **org.springframework.boot.test.context.SpringBootTest**, **org.springframework.boot.test.web.server.LocalServerPort**, and **org.junit.jupiter.api.Test**, plus **spring-boot-starter-test** in test scope.

Production apps also need load tests covering: connections opened/sec, active connections, p95/p99 message latency, throughput, buffer occupancy, reconnect storms, dropped messages, and memory per connection.

## 20. Common Troubleshooting Guide

| Symptom | Where to Check | How to Fix |
| --- | --- | --- |
| **404 /ws/echo** | Missing `@EnableWebSocket`, wrong registry path, different context path/proxy rewrite | Verify `WebSocketConfigurer` and handshake URL. |
| **400 Bad Request** on plain curl GET | Not a WebSocket handshake | Use browser WebSocket API or a frame-capable Java client. |
| **403 Forbidden** when opening socket from another frontend | Origin not in allowlist, security rules, or proxy policy | Check real `Origin` and `allowedOrigins`; avoid reckless wildcards. |
| **401 Unauthorized** | Servlet security requires login, cookie/token missing from handshake | Check auth flow, cookie attributes, and endpoint matchers. |
| **101 on localhost, 502 through CDN/Nginx** | Proxy not forwarding Upgrade/Connection or lacking WS support | Check `proxy_http_version 1.1`, headers, and upstream logs. |
| **wss TLS certificate errors** | Invalid TLS termination/certificate/hostname | Configure valid HTTPS/TLS; never disable certificate verification in production. |
| **Mixed Content on HTTPS page** | HTTPS page trying to open cleartext `ws://` | Use `wss://` and ensure endpoint is served over TLS. |
| **Connection closes after 60s idle** | Container idle timeout, proxy/NAT policy, missing heartbeats | Measure which hop closes it and align timeouts/heartbeats. |
| **Close code 1009** | Message/file exceeded container or app size limit | Reduce payload, use protocol chunking, or raise limits carefully. |
| **afterConnectionClosed not firing immediately on cable unplug** | Unclean TCP disconnect; detected only on timeout/write | Add heartbeats/idle timeouts and fault-tolerant cleanup. |
| **Some users miss broadcasts across two pods** | Node-local registry without a message backplane | Add pub/sub/broker/cross-node events. |
| **Concurrent send throws exception or lags** | Multiple producers writing concurrently to one raw WebSocketSession | Use one `ConcurrentWebSocketSessionDecorator` per session with buffer limits. |
| **@MessageMapping added but raw handler never sees it** | `@MessageMapping` belongs to STOMP messaging stack | Use STOMP broker config properly; do not mix with raw handlers. |
| **WebFlux handler won't plug into MVC registry** | Wrong package import / reactive vs. Servlet mismatch | Identify active web application type and matching API stack. |
| **Cannot inject Jakarta classes in older WAR container** | `javax`/`jakarta` mismatch or unsupported container version | Align Spring Boot and Servlet container versions. |
| **REST GET works yet WS rejected at ingress** | Ingress route supports regular HTTP without Upgrade/long timeouts | Check WS route, host/headers, and idle timeout. |

## 21. Hands-On Exercises and Extension Ideas

**Exercise 1 – Character/byte-limited echo:** modify the handler to allow at most 512 UTF-8 bytes. Send a 512-byte ASCII string, then a 513-byte one. Expect the first to echo and the second to close with code 1009 if received by the handler.

**Exercise 2 – Verifying allowedOrigins:** serve an HTML page on **http://localhost:5173**, open **ws://localhost:8080/ws/echo**, and verify success. Serve from **http://localhost:3000** and confirm rejection since that origin is not allowlisted. Never use a non-browser client spoofing `Origin` as a substitute for testing browser policy.

**Exercise 3 – Observing idle timeout:** leave the browser open without sending messages and observe the close code and timing. Compare against the 60-second container config and any proxy timeout. Do not assume identical exact timings across every OS/container, as it depends on transport activity and lifecycle.

**Exercise 4 – Client reconnect:** add backoff + jitter on the frontend. Distinguish transient network failures from policy-violation close codes. After a successful reconnect, fetch/recover data state rather than assuming missed events auto-replay.

**Exercise 5 – Per-message authorization:** with a Spring Security session, implement a JSON command **{"type":"subscribeOrder","orderId":42}** and verify the user is authorized to view that order before subscribing. Never trust `orderId` or roles supplied by the client; look up ownership/ACL server-side.

**Exercise 6 – Multiple replicas:** run two instances behind a load balancer. Connect one client to each instance, emit an event on one node only, and explain why the other node doesn't deliver it. Design a pub/sub backplane and at-least-once/dedup rules.

**Exercise 7 – Moving to STOMP for pub/sub:** map a separate endpoint **/ws-stomp**, enable a `/topic` simple broker, and add an `@MessageMapping`. Contrast STOMP SEND/SUBSCRIBE with raw WebSocket text frames, and verify inbound subscription security.

## 22. Self-Check Questions

**1. Can you use @GetMapping("/ws/echo") to handle every WebSocket message?**  
No. GET applies only to the initial HTTP handshake; after upgrade, messages flow through `WebSocketHandler` or the messaging layer.

**2. Which dependency is needed in Spring Boot MVC?**  
Use **spring-boot-starter-websocket** alongside Servlet MVC configuration; embedded Tomcat/Jetty/Undertow provide platform WebSocket support.

**3. Does @EnableWebSocket expose all endpoints automatically?**  
No. You need `WebSocketConfigurer` to register handlers at specific paths.

**4. Why does WebSocket return 101 instead of 200?**  
It is the handshake response switching from HTTP/1.1 to the WebSocket protocol.

**5. Should a browser on an HTTPS page open ws:// or wss://?**  
Normally **wss://** for TLS encryption and to prevent mixed-content blocking; the public endpoint must serve valid TLS.

**6. Is allowedOrigins authentication or authorization?**  
No. It reduces cross-site browser initiation risks; non-browser clients can spoof `Origin`. Real authentication and authorization are still mandatory.

**7. Are WebSocketSession and HttpSession the same object?**  
No. `WebSocketSession` represents the socket connection; `HttpSession` holds HTTP session state. Context can be copied during the handshake, but lifecycles differ.

**8. After the handshake, do Spring Security Servlet filters re-run for every WebSocket message?**  
Not as fresh HTTP requests. The handler or messaging layer must authorize messages/subscriptions.

**9. Why shouldn't multiple threads send concurrently on the same WebSocketSession?**  
Because the underlying transport may not support concurrent writes; serialize sends or use `ConcurrentWebSocketSessionDecorator` with buffer/time limits.

**10. Does an 8 KiB container buffer replace a 1 KiB business limit?**  
No. They are two separate layers; the demo enforces payload bytes in the handler while the server container enforces its own buffer limits.

**11. Why might 101 succeed on localhost yet fail behind Nginx?**  
The proxy may fail to forward Upgrade/Connection headers, mismatch route/host, or close idle connections prematurely.

**12. Does raw WebSocket include SUBSCRIBE /topic out of the box?**  
No. That is STOMP/message-broker semantics; raw handlers must define their own protocol if desired.

**13. Does the simple STOMP broker provide durable cross-node broadcasting?**  
No. The simple broker is in-memory and unsuitable for clustered or durable delivery.

**14. Does WebSocket automatically replay messages after reconnect?**  
No. Applications must build event IDs/acks/storage or a resynchronization flow.

**15. Is WebSocket always faster than HTTP polling in every case?**  
No. Evaluate update frequency, client counts, proxy compatibility, load, and long-lived connection costs.

## 23. Servlet WebSocket Deployment Checklist

- [ ] Confirm the app runs **Spring Boot Servlet MVC**, without accidentally importing reactive WebSocket types.
- [ ] Add **spring-boot-starter-websocket** and verify embedded Tomcat/Jetty/Undertow compatibility.
- [ ] Use **@EnableWebSocket**, **WebSocketConfigurer**, and **WebSocketHandler** for raw endpoints.
- [ ] Assign stable paths like **/ws/echo**; never use `@GetMapping` to receive frames.
- [ ] Verify **101** handshakes, WebSocket text/binary frames, and close events via browser and Java clients.
- [ ] Configure **setAllowedOrigins** strictly to frontend origins; never confuse `ws://` endpoints with `http(s)` Origins.
- [ ] For sensitive endpoints, authenticate the handshake, authorize messages/subscriptions, and defend against CSWSH.
- [ ] Use **wss://** for public clients with valid TLS certificates, hostnames, and trust chains.
- [ ] Configure **ServletServerContainerFactoryBean** and app payload limits based on actual resources.
- [ ] Cap active connections, message sizes, send buffers, concurrent writes, and send rates.
- [ ] Implement idle timeouts/heartbeats, backoff reconnect policies, and post-disconnect state recovery.
- [ ] Verify Nginx/ingress/CDN forwards Upgrade/Connection and supports long connection timeouts.
- [ ] Separate REST/CORS policies from WebSocket Origin/handshake rules; never assume OPTIONS preflight governs native WebSocket.
- [ ] Across multiple replicas, introduce an event bus/broker to sync messages between nodes.
- [ ] When STOMP is needed, use **@EnableWebSocketMessageBroker** and messaging security without mixing raw handlers.
- [ ] Test via browser, Java WebSocket client, real proxies, and concurrent load.
- [ ] Never log tokens, cookies, or sensitive raw payloads; monitor 101/4xx rates, active connections, close codes, latency, bytes, and reconnect storms.
- [ ] When deploying as a WAR, verify container Jakarta WebSocket support; omit `ServerEndpointExporter` when using raw Spring `WebSocketHandler` without `@ServerEndpoint`.

## 24. Official Documentation Sources

- **Spring Boot 3.3 – Messaging / WebSockets:** https://docs.spring.io/spring-boot/docs/3.3.x/reference/html/messaging.html — embedded Servlet WebSocket auto-configuration, `starter-websocket`, and WAR deployment.
- **Spring Framework – WebSocket Overview (Servlet stack):** https://docs.spring.io/spring-framework/reference/web/websocket.html — HTTP Upgrade, RFC 6455, use cases, and WebSocket vs. HTTP.
- **Spring Framework – WebSocket Server API:** https://docs.spring.io/spring-framework/reference/web/websocket/server.html — `WebSocketHandler`, `@EnableWebSocket`, `WebSocketConfigurer`, `HandshakeInterceptor`, allowed origins, `ServletServerContainerFactoryBean`.
- **Spring Framework – STOMP Enable:** https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html — `@EnableWebSocketMessageBroker`, STOMP endpoints, broker prefixes.
- **Spring Framework – STOMP Simple Broker:** https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html — in-memory broker, heartbeats, and limitations.
- **Spring Framework – STOMP External Broker:** https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html — broker relay and cluster considerations.
- **Spring Security – WebSocket Security (Servlet):** https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html — authentication from HTTP Principal, message authorization, same-origin/CSRF, and SockJS.
- **Spring Framework – ServletServerContainerFactoryBean Javadoc:** https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/socket/server/standard/ServletServerContainerFactoryBean.html — max buffer sizes, idle timeout, async send timeout.
- **RFC 6455 – The WebSocket Protocol:** https://www.rfc-editor.org/rfc/rfc6455 — handshake and frames.
- **RFC 8441 – Bootstrapping WebSockets with HTTP/2:** https://www.rfc-editor.org/rfc/rfc8441 — extended CONNECT over HTTP/2.
- **MDN – WebSocket API:** https://developer.mozilla.org/en-US/docs/Web/API/WebSocket — browser WebSocket constructor, events, and `readyState`.
