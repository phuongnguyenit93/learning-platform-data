# SockJS Fallback and Constraints Through Proxies

## 1. Objectives and Scope

WebSocket creates a long-lived, bidirectional communication channel between the browser and the server. However, the real network path typically traverses browser → corporate proxy/CDN → load balancer or reverse proxy → Spring application. A proxy might fail to forward WebSocket Upgrade, close seemingly idle connections, or buffer HTTP responses so streaming data does not reach the browser in time.

**SockJS** is a protocol that emulates WebSocket semantics, preferring WebSocket when possible and falling back to suitable **HTTP transports** (HTTP streaming or long polling) when needed. Spring Framework provides a SockJS server on the **Servlet stack** with STOMP messaging integration. SockJS cannot fix every network error, does not provide a message broker on its own, and does not replace proper reverse proxy configuration.

After this lesson, you will:
- Understand the transport selection sequence: `/info` → WebSocket → streaming/polling, and why fallbacks can still fail.
- Distinguish WebSocket Upgrade from SockJS HTTP GET/POST calls; know which paths and headers proxies must not block.
- Configure Spring MVC + STOMP + SockJS and a browser client with a runnable Java 17/Spring Boot 3.3.x example.
- Evaluate timeouts, buffering, heartbeats, CORS, Origin, cookies, CSRF, and security when a reverse proxy/LB sits in the middle.
- Understand sticky sessions and the limits of the simple STOMP broker when scaling across multiple instances.
- Reproduce failures and test **the actual fallback transport**, rather than concluding everything works from a single successful WebSocket handshake.

### Do you really need SockJS?

Most modern browsers support WebSocket. If your network, proxies, and client devices reliably support WebSocket, **STOMP over native WebSocket is usually simpler**: fewer paths, fewer extra requests, and lower compatibility overhead. Enable SockJS only if you must support networks that block WebSocket or a known set of legacy clients. Do not enable SockJS out of habit merely because the app uses STOMP.

## 2. Protocol Layers to Distinguish

| Layer | Role | Example |
| --- | --- | --- |
| TCP/TLS | Transport connection; HTTPS/WSS encrypts the wire | Browser ↔ proxy |
| HTTP / WebSocket handshake | Upgrade from HTTP to WebSocket; or regular HTTP requests | GET + Upgrade, status 101 |
| SockJS | Selects WebSocket or emulates over HTTP; manages transport-level sessions/frames | `/ws/info`, `/ws/{server}/{session}/xhr` |
| STOMP | SEND/SUBSCRIBE/MESSAGE protocol on top of the open channel | SUBSCRIBE `/topic/greetings` |
| Spring application | Handles messages in `@MessageMapping` and publishes via broker | `/app/hello` |

**SockJS is not synonymous with STOMP.** You can use SockJS with a `WebSocketHandler` without STOMP. Conversely, you can use STOMP over native WebSocket without SockJS. When an app configures `registry.addEndpoint("/ws").withSockJS()`, `/ws` is the **HTTP base URL of the SockJS endpoint**, not a STOMP destination address. STOMP clients typically use `webSocketFactory` to instantiate SockJS and send STOMP frames over that connection.

### 2.1. SockJS connection flow

Suppose the application exposes endpoint `/ws`:

1. The browser calls `GET https://example.org/ws/info`. The JSON response reports server capabilities such as `websocket`, `cookie_needed`, and entropy. The `/info` URL must reach the server; a 404/403/502 here can kill the connection **before** WebSocket is even attempted.
2. If browser/network conditions permit, SockJS attempts WebSocket at a session-scoped path. The proxy must forward the handshake and then maintain a bidirectional channel.
3. If WebSocket is unavailable, SockJS can use HTTP streaming: one request stays open for server-to-client pushes, while separate HTTP POST requests send data upstream.
4. If streaming is unavailable, the client can switch to HTTP long polling: holding a receive request open until data or timeout returns, then opening the next request; upstream sends remain separate requests.
5. Once the channel opens, the STOMP client sends CONNECT, then SUBSCRIBE/SEND as usual. Changing transport does not change destinations or server-side `@MessageMapping`.

**There is no guarantee** that every client will always "fail WebSocket and succeed via polling". CORS, cookies, streaming proxies, authentication, session affinity, network policies, and connection limits can all break fallbacks. The SockJS client decides the list of enabled transports; restrict transports during testing to verify each path explicitly.

### 2.2. URL structure and sessions

Transport requests typically fall under:

~~~text
https://example.org/ws/{server-id}/{session-id}/{transport}
~~~

Example HTTP-level URLs (illustrative, not a real session):

~~~text
GET  /ws/info
GET  /ws/123/sessionABC/websocket       # WebSocket Upgrade
POST /ws/123/sessionABC/xhr             # Receive data via long polling
POST /ws/123/sessionABC/xhr_send        # Send data via HTTP
POST /ws/123/sessionABC/xhr_streaming   # Receive streaming data
~~~

In **SockJS client transport names**, you may see `xhr-polling` or `xhr-streaming`, whereas the **actual HTTP path segments** in the protocol are `xhr`, `xhr_send`, and `xhr_streaming`. Use the Network tab to inspect real names; never configure a proxy to allow only `/ws/websocket`.

- `server-id`: a URL segment that can assist load balancer routing rules; by itself it **does not** guarantee the same session always reaches the same backend.
- `session-id`: correlates HTTP requests belonging to the same SockJS session. A long polling connection issues multiple requests sharing this ID.
- `transport`: the transport mechanism, affecting HTTP method, connection duration, and response framing.
- STOMP destinations like `/topic/greetings` **are not HTTP URLs for proxy rewriting**; they live inside STOMP frame payloads.

SockJS frames may begin with `o` (open), `h` (heartbeat), `a["..."]` (array of messages), or `c[...]` (close). This is the SockJS framing layer; STOMP frames sit inside the payload. Seeing `o` in the Network tab only proves the SockJS session opened—**it does not prove STOMP CONNECT and SUBSCRIBE succeeded**.

## 3. Spring Server: Enabling SockJS Properly

To use STOMP on Spring MVC, configure `@EnableWebSocketMessageBroker`, choose an HTTP endpoint, and define destinations. Minimal template:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
            .withSockJS();
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
~~~

This is an integration configuration snippet; imports belong to `org.springframework.context.annotation` and `org.springframework.web.socket.config.annotation`. `withSockJS()` enables fallback transports; if omitted, you have a native WebSocket endpoint and clients connect via `ws://`/`wss://` URLs instead of a SockJS HTTP base URL.

A controller:

~~~java
@Controller
public class GreetingController {
    @MessageMapping("/hello")
    @SendTo("/topic/greetings")
    public Greeting greet(HelloMessage message) {
        return new Greeting("Hello, " + message.name());
    }
}
~~~

`HelloMessage`/`Greeting` are application DTOs. Client SENDs to `/app/hello` are routed to `@MessageMapping("/hello")`; subscribers to `/topic/greetings` receive the result. The proxy does not need to know about these STOMP destinations.

**CORS/Origin:** by default Spring WebSocket/SockJS accepts same-origin only. If the web UI is at `https://app.example.org` and the backend is at `https://api.example.org`, you must intentionally design cross-origin, authentication, and cookie handling. Endpoint example:

~~~java
registry.addEndpoint("/ws")
    .setAllowedOrigins("https://app.example.org")
    .withSockJS();
~~~

The snippet above illustrates **a single trusted origin**; do not casually use `"*"` with credentials. When origins are explicitly restricted, some SockJS iframe transports that cannot enforce Origin checks may be disabled. Browsers can normally fall back via XHR without iframes; test with your product's real clients.

### Why is a SockJS server different from a WebFlux reactive endpoint?

`withSockJS()` and the STOMP broker in this example belong to Spring Framework's **Servlet / Spring MVC** stack. Do not copy this configuration into a WebFlux-only handler and expect equivalent SockJS fallback behavior. Choose the matching stack, starter, and annotations. Under high load, HTTP long polling/streaming consumes resources differently than native WebSocket; measure threads, connections, and memory for your deployment stack.

## 4. Reverse Proxy: Both Traffic Patterns Must Work Together

### 4.1. WebSocket Upgrade

An HTTP/1.1 WebSocket handshake typically looks like:

~~~http
GET /ws/123/sessionABC/websocket HTTP/1.1
Host: example.org
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: ...
Sec-WebSocket-Version: 13
~~~

`101 Switching Protocols` indicates the server accepted the Upgrade. `Upgrade` and `Connection` are hop-by-hop headers; the proxy must be configured to forward them properly upstream. After 101, the proxy must keep the bidirectional channel open rather than treating individual frames as separate HTTP requests.

**Do not blindly copy `Connection: Upgrade` onto every HTTP request.** Normal GET `/info` or POST polling requests do not perform an Upgrade handshake; proxy configs should use a `map` to select the value based on `$http_upgrade`.

### 4.2. HTTP streaming and polling

When WebSocket is disallowed, the proxy must still:
- Permit `GET /ws/info`, CORS `OPTIONS` when needed, and HTTP `POST` for polling/streaming/sending. Do not route SockJS exclusively for WebSocket GETs.
- Forward **all sub-paths under `/ws/`** intact without stripping `{server-id}/{session-id}`. Pay close attention to whether `proxy_pass` has a trailing slash, as that alters URI forwarding in NGINX.
- Never cache `/info`, session frames, or stateful polling/streaming responses.
- Disable response buffering for streaming, because buffering can hold data until a threshold fills, making the browser think the connection is silent.
- Allow requests/responses to stay open longer than typical HTTP REST calls. Check timeouts at *every layer*: CDN/LB, reverse proxy, backend, and client.
- Preserve query strings, HTTP methods, cookies, Content-Type, Origin, and headers required for CORS/authentication.
- Route multiple HTTP requests belonging to the same session to the same backend, or implement an appropriate session-routing strategy.

**Streaming** is especially sensitive to proxy buffering; **polling** is especially sensitive to request counts, sticky sessions, CORS, and concurrent connection limits. A configuration that works for 101 does not automatically work for `xhr_streaming`/`xhr`.

### 4.3. Illustrative NGINX example

This is a fragment to integrate into an existing NGINX configuration; assume a `server` block already serves `example.org` and the Spring app listens on `127.0.0.1:8080`. Place `map` inside the `http` context and `location` inside the `server` context:

~~~nginx
# Place inside http { ... }
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# Place inside server { ... } for example.org
location /ws/ {
    # No trailing / on proxy_pass: preserve /ws/... for Spring.
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;

    proxy_buffering off;       # Critical for SockJS HTTP streaming
    proxy_cache off;
    proxy_read_timeout 75s;    # Example: must verify against actual heartbeat
    proxy_send_timeout 75s;
}
~~~

This fragment **is not a standalone NGINX config**; you still need listeners, TLS/certificates, other routes, security, and load balancer settings for your real system. If the route is mounted under a different prefix (e.g. public `/api/ws` while Spring uses `/ws`), design proper rewrites and forwarded headers rather than guessing trailing slashes during deployment.

In HTTPS production environments, browsers access SockJS over `https://example.org/ws`; internal WebSocket transport uses `wss://` from the browser with TLS termination at the edge. Never mix an HTTPS page with insecure `http://`/`ws://` endpoints due to mixed-content policy. Ensure upstream receives accurate scheme/host info if the app generates absolute URLs; trust `X-Forwarded-*` headers only from controlled reverse proxies.

**The 75s value** in this example is not a universal standard. Some environments terminate idle connections at 30/60/120 seconds; set timeouts above the data/heartbeat cadence with a safety margin, while still respecting resource limits and application timeouts. Also verify idle timeouts on any LB in front of NGINX, since NGINX cannot override limits enforced by an outer hop.

## 5. Heartbeats, Session Lifecycle, and Timeouts

SockJS uses an `h` heartbeat frame so proxies do not treat quiet connections as dead. In Spring's common default configuration, SockJS heartbeats are emitted roughly every **25 seconds** when no other messages are sent. This can be changed with:

~~~java
registry.addEndpoint("/ws")
    .withSockJS()
    .setHeartbeatTime(25_000);
~~~

This snippet integrates into `registerStompEndpoints`; the value is in **milliseconds**. When a STOMP client and server negotiate STOMP heartbeats, Spring typically stops sending independent SockJS heartbeats. Therefore **do not assume an `h` frame always arrives every 25 seconds**. When analyzing timeouts, inspect the **actual wire traffic** sent on the connection (STOMP heartbeats, SockJS heartbeats, or other messages).

Related limits:
- **Proxy read/idle timeout:** if too short, it can sever WebSocket or streaming even while the app is healthy.
- **Heartbeat scheduler:** an undersized thread pool can delay heartbeats under heavy load; monitor and size appropriately.
- **Disconnect delay:** for HTTP polling, brief gaps between receive requests should not cause the server to expire the session prematurely on slow networks.
- **Stream bytes limit/message cache:** streaming requests may close and reopen to bound memory buffers; polling may need to cache messages between requests.
- **Client reconnect delay:** reconnecting creates a new session, requiring re-SUBSCRIBE and deciding whether messages missed during the outage need replay/ACK.

SockJS does not provide exactly-once delivery or history replay guarantees. If a chat or trading app cannot lose messages, the business layer must implement sequence IDs, ACKs, snapshot/replay, or a durable broker as required.

## 6. Load Balancers, Sticky Sessions, and Clustering

SockJS HTTP fallback normally issues multiple requests for the same `session-id`: receive requests, send requests, and subsequent receives. SockJS session state lives on the server instance that created it. If an LB sprays requests randomly across Spring instances, instance B will not find the session created by instance A. Common symptoms: initial connection succeeds then `404` on `xhr_send`, abnormal closures, or reconnect loops.

~~~mermaid
flowchart LR
    B[Browser SockJS] --> L[Load balancer]
    L -->|info / first request| A[Spring instance A]
    L -.->|xhr_send same session, wrong route| C[Spring instance B]
    A --- M[Session on A]
    C --- E[No session on B]
~~~

**Sticky sessions / session affinity** are the standard solution: requests belonging to the same SockJS session route to the same instance. The LB can use an affinity cookie or explicit route mapping; the `server-id` segment in the URL only helps if the LB **is actually configured with rules to use it**. Do not assume SockJS solves sticky sessions automatically.

Two distinct problems must be solved separately:
1. **Transport/session routing:** routing the same SockJS session to the right node. Sticky routing preserves transport session state.
2. **Distributing messages across nodes:** `enableSimpleBroker` is an in-memory broker inside a single application and **is not a shared cluster broker**. When cross-instance subscriptions and complex routing are needed, evaluate an external STOMP broker/relay and a matching message distribution architecture. Adding a broker relay **does not eliminate** the requirement that HTTP requests of a single SockJS session hit the same node.

If a node dies, sticky sessions cannot rescue sockets/sessions connected to that node. Clients must reconnect, re-authenticate, and re-subscribe; the application must handle recovery of missed data.

## 7. Origin, CORS, Cookies, CSRF, and Authentication Through Proxies

### 7.1. Origin and CORS

A WebSocket handshake carries an `Origin` header, though browser WebSockets do not enforce the exact same-origin rules as `XMLHttpRequest`. Spring enforces allowed origins on endpoints; Spring Security can add controls during STOMP CONNECT processing.

SockJS HTTP fallbacks over XHR/polling follow browser CORS rules. Cross-origin requests may trigger **OPTIONS preflight** before POST; proxies/WAFs must not block them indiscriminately. Spring SockJS can add CORS headers automatically if the app has not already added them. If a filter/gateway already sets CORS headers, avoid emitting duplicate conflicting `Access-Control-Allow-Origin` values. When using cookies, `Access-Control-Allow-Origin: *` cannot be combined with credentialed CORS requests.

Items to verify:
- The `Origin` sent by the browser is the UI page's origin, not always the backend's `Host`.
- `Access-Control-Allow-Credentials`, `SameSite`/`Secure` cookies, and third-party cookie policies can let WebSocket auth work while polling fails.
- CORS is a browser policy. Non-browser clients can spoof `Origin`; server-side authorization remains mandatory.
- Keep origin allowlists short and explicit, use HTTPS, and avoid overly broad patterns.

### 7.2. Cookies and session state

The `/info` request may return `cookie_needed`, influencing SockJS transport decisions. In Java Servlets, `JSESSIONID` is commonly used; this does not mean every app must use session cookies. If JWTs are used, clarify where the token travels: the browser WebSocket API restricts setting arbitrary custom HTTP headers; SockJS XHR and STOMP CONNECT have different constraints as well. Never pass tokens casually in query strings because URLs end up in logs, analytics, and proxies.

Proxies must forward cookies when session/auth depends on them. With cookie-based LB stickiness, verify the browser sends the cookie on `/ws/.../xhr` and `/xhr_send` HTTP requests. The `JSESSIONID` header may assist affinity, but its presence alone does not prove LB stickiness is enabled.

### 7.3. CSRF and iframes

With Spring Security STOMP, CSRF protection on `CONNECT` defends against cross-site connections reusing session cookies. With SockJS HTTP fallbacks, `CONNECT` rides inside the transport payload; you cannot simply attach a CSRF token via a SockJS HTTP header option like a REST call. Per Spring Security documentation, pass the CSRF token in **STOMP connect headers**, and if HTTP CSRF exemptions are needed, scope them **strictly to the relevant SockJS endpoints**, never site-wide.

Legacy iframe transports can also clash with `X-Frame-Options: DENY` or CSP `frame-ancestors`. If same-origin iframes are genuinely required, use an appropriate policy like SAMEORIGIN and vet where the SockJS client library is loaded from. With restricted allowed origins, Spring may disable iframe transports that cannot enforce origin checks. **Do not weaken default security just to support obsolete browsers**; define your supported browser matrix and test it.

## 8. Complete Java 17 + Spring Boot 3.3 Example: WebSocket and Forced xhr-polling

This example provides a Spring Boot app, a STOMP echo endpoint, an HTML client using SockJS + STOMP, and a `/ws/info` test. The web page includes a URL parameter to **force XHR long polling**, proving the HTTP fallback truly works rather than testing only native WebSocket.

Requirements: **JDK 17+**, Maven, and a browser able to load two JS libraries from a CDN. The backend runs once Maven dependencies are resolved; for completely offline browser usage, host both JS libraries from the app's static assets instead of a CDN in accordance with your project's licensing and operational policies. The example pins Spring Boot `3.3.13` for compatibility with Spring Framework 6.1 APIs and Java 17; new applications should consider a currently supported Spring Boot release line.

### 8.1. Directory layout

~~~text
sockjs-proxy-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/SockJsDemoApplication.java
    │   └── resources/static/index.html
    └── test/
        └── java/demo/SockJsInfoTest.java
~~~

### 8.2. pom.xml

~~~xml
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
    <groupId>demo</groupId>
    <artifactId>sockjs-proxy-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

`spring-boot-starter-websocket` provides Spring MVC WebSocket/STOMP support and compatible Jackson bindings. No WebFlux or external broker server is needed for this single-instance demo.

### 8.3. src/main/java/demo/SockJsDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@SpringBootApplication
public class SockJsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SockJsDemoApplication.class, args);
    }

    public record HelloMessage(String name) {}
    public record Greeting(String content) {}

    @Configuration
    @EnableWebSocketMessageBroker
    public static class WsConfig implements WebSocketMessageBrokerConfigurer {

        @Override
        public void registerStompEndpoints(StompEndpointRegistry registry) {
            // Same-origin only; cross-origin must be configured intentionally.
            registry.addEndpoint("/ws")
                .withSockJS()
                .setHeartbeatTime(25_000);
        }

        @Override
        public void configureMessageBroker(MessageBrokerRegistry registry) {
            registry.setApplicationDestinationPrefixes("/app");
            registry.enableSimpleBroker("/topic");
        }
    }

    @Controller
    public static class GreetingController {
        @MessageMapping("/hello")
        @SendTo("/topic/greetings")
        public Greeting greet(HelloMessage input) {
            return new Greeting("Hello, " + input.name());
        }
    }
}
~~~

Explanation: `/ws` accepts SockJS/transport connections; `/app/hello` is the STOMP SEND destination routed to `GreetingController`; `/topic/greetings` is subscribed via the simple broker. `Greeting` is serialized to JSON by Jackson from the Java record. The example intentionally omits authentication to focus on localhost transport behavior. **Never expose the demo endpoint as a production chat service** without adding authentication, authorization, and message validation.

### 8.4. src/main/resources/static/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SockJS transport demo</title>
</head>
<body>
  <h1>SockJS + STOMP</h1>
  <p id="state">Initializing...</p>
  <button id="send" disabled>Send greeting</button>
  <pre id="log"></pre>

  <script src="https://cdn.jsdelivr.net/npm/sockjs-client@1.6.1/dist/sockjs.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/@stomp/stompjs@7.2.0/bundles/stomp.umd.min.js"></script>
  <script>
    const status = document.getElementById("state");
    const button = document.getElementById("send");
    const log = document.getElementById("log");
    const forcePolling =
      new URLSearchParams(window.location.search).get("transport") === "polling";

    const client = new StompJs.Client({
      // SockJS takes an HTTP(S) URL, do not pass ws:// like native WebSocket.
      webSocketFactory: () => new SockJS(
        "/ws",
        null,
        forcePolling ? { transports: ["xhr-polling"] } : {}
      ),
      reconnectDelay: 3000,
      heartbeatIncoming: 10000,
      heartbeatOutgoing: 10000,
      onConnect: () => {
        status.textContent = forcePolling
          ? "Connected to STOMP via xhr-polling"
          : "Connected to STOMP via SockJS";
        button.disabled = false;
        // Place SUBSCRIBE inside onConnect because reconnect creates a new session.
        client.subscribe("/topic/greetings", frame => {
          const body = JSON.parse(frame.body);
          log.textContent += body.content + "\n";
        });
      },
      onWebSocketClose: () => {
        button.disabled = true;
        status.textContent = "Connection closed; retrying reconnect...";
      },
      onStompError: frame => {
        status.textContent = "Broker reported error: " + frame.headers.message;
      }
    });

    button.addEventListener("click", () => {
      client.publish({
        destination: "/app/hello",
        body: JSON.stringify({ name: "Spring" }),
        headers: { "content-type": "application/json" }
      });
    });

    client.activate();
  </script>
</body>
</html>
~~~

The two JavaScript files from the CDN require Internet access on initial load (or self-host them accordingly). Default mode lets SockJS choose the transport; `?transport=polling` forces `xhr-polling`, useful for proxy testing. `reconnectDelay` and STOMP heartbeats are demo settings; real deployments need load-appropriate reconnection, auth/CSRF, and backoff strategies.

### 8.5. Test verifying the info endpoint

**src/test/java/demo/SockJsInfoTest.java**:

~~~java
package demo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SockJsInfoTest {

    @LocalServerPort
    int port;

    @Test
    void sockJsInfoEndpointResponds() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("http://localhost:" + port + "/ws/info"))
            .GET()
            .build();

        HttpResponse<String> response = HttpClient.newHttpClient().send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"websocket\""));
    }
}
~~~

This test starts Spring Boot on a random port, sends a real HTTP request, and verifies `/ws/info` responds with the `websocket` field. It **does not automatically test every fallback transport**, STOMP subscriptions, proxies, or load balancers; the dedicated test steps in the next section cover those layers.

### 8.6. Running the application and observing results

In `sockjs-proxy-demo`:

~~~bash
mvn test
mvn spring-boot:run
~~~

`mvn test` is expected to succeed (exit code 0) when `SockJsInfoTest` passes. The second command starts the server; the terminal holds the Spring Boot process. Unless configured otherwise, the app listens on `localhost:8080`. Open in a browser:

~~~text
http://localhost:8080/
http://localhost:8080/?transport=polling
~~~

On each page, after connecting successfully, click **Send greeting**. The log displays a line generated by the application:

~~~text
Hello, Spring
~~~

This result appears after the client executes CONNECT → SUBSCRIBE `/topic/greetings` → SEND `/app/hello` and receives MESSAGE. The page displays different status text depending on the transport mode. Open DevTools → Network:
- Default page: typically shows `GET /ws/info` and an upgraded WebSocket request `.../websocket`.
- `?transport=polling` page: shows `GET /ws/info`, `POST .../xhr`, and `POST .../xhr_send`; **no 101 Upgrade is required** to exchange STOMP frames.
- If CDN scripts are blocked by browser/firewall policies, the page cannot run the test; inspect Console JS load errors before diagnosing the backend.

Test the backend without a browser:

~~~bash
curl -i http://localhost:8080/ws/info
~~~

Expect **HTTP 200** and JSON containing SockJS info such as `"websocket": true`. Other fields and `entropy` vary per call; **do not match the entire JSON body as a fixed string**.

## 9. Testing Through a Reverse Proxy and Reproducing Failures

Do not conclude a proxy works properly if tests only hit `localhost:8080` directly: that bypasses NGINX/CDN/LB. Run both URLs **through the public hostname** (HTTPS) after configuring the proxy.

### Mandatory test matrix

| Scenario | How to execute | Success signal |
| --- | --- | --- |
| SockJS info | GET `https://host/ws/info` | 200, JSON served through proxy |
| WebSocket preferred | Default browser; inspect WS tab | 101, STOMP CONNECT/SUBSCRIBE/SEND and MESSAGE received |
| Polling forced | `?transport=polling` through proxy | POST xhr/xhr_send succeed, MESSAGE received |
| Streaming | Restrict client transports to xhr-streaming in a dedicated test | Data frames reach browser promptly without waiting for a full buffer |
| Intentional WebSocket block | Test behind a proxy that disallows Upgrade | Fallback succeeds if network still allows HTTP transport |
| Idle wait | Hold connection across multiple heartbeat intervals | Not dropped prematurely by proxy |
| Two Spring instances | Behind an LB with configured affinity | Session requests consistently route to the same node |
| Different Origin | UI on allowed origin vs. disallowed origin | Allowed origin works; unknown origin is rejected |
| Cookies/CSRF | Environment with Spring Security | STOMP CONNECT and HTTP fallback obey security policies |
| Reconnect | Pause network then restore | New session opens, re-SUBSCRIBEs, data follows recovery strategy |

**Forcing `xhr-streaming`:** change the client config line to `{ transports: ["xhr-streaming"] }` in a dedicated test build; do not leave this in production code. The Network tab reveals when `xhr_streaming` delays delivering data due to proxy buffering. If a transport is blocked, that test will fail—providing concrete evidence of the environment's constraints.

### Symptom-based diagnosis

1. **`/ws/info` returns 404:** check Spring context path, location/rewrite rules, and `proxy_pass` path; requests are not reaching the SockJS endpoint.
2. **`/ws/info` returns 403:** check Origin, CORS filters, Spring Security, and CSRF for HTTP methods; do not hastily open `"*"` site-wide.
3. **101 Upgrade does not happen, only WebSocket fails:** check `Upgrade`/`Connection` and HTTP/1.1 upstream, whether CDN/LB permits WebSocket, and proper TLS scheme.
4. **WebSocket works but polling fails:** check HTTP POST/OPTIONS, CORS, cookies, `/ws/{server}/{session}/xhr*`, WAF rules, body limits, and affinity.
5. **Streaming delivers batches of messages late:** proxy buffering/caching may be holding bytes; disable buffering only on required routes and measure frame timing.
6. **Connections drop regularly every ~30s or ~60s:** compare proxy/LB idle timeouts against actual transmitted heartbeats, not just configured values.
7. **One node works, two nodes fail mid-send:** inspect session-id routing, cookie affinity, and broker state; do not immediately blame the SockJS client.
8. **CONNECT fails after HTTP 200:** a SockJS open frame does not mean STOMP auth/CSRF passed the broker; check STOMP ERROR frames and Spring message security.
9. **HTTPS page hitting HTTP endpoint:** mixed-content block; must use HTTPS SockJS URL / WSS native WebSocket.
10. **Infinite reconnect loops and rising load:** enforce reconnect backoff, rate limits, and session timeouts; prevent reconnect storms when upstream dies.

### Metrics to collect

- Session open/close counts, transport distribution (WebSocket/xhr_streaming/xhr), fallback success rate.
- Statuses/errors on `/ws/info`, `.../websocket`, `.../xhr`, `.../xhr_send`; proxy 499/502/504 counts and wait times.
- Number of currently open WebSocket and long polling/streaming connections; queues/message buffers, memory, and thread usage.
- STOMP CONNECT successes/errors, SUBSCRIBE counts, message latency, reconnect attempts.
- Per cluster node: routed sessions, sticky affinity hits/misses, unknown-session errors.
- Separate **transport metrics** (HTTP/SockJS) from **application message metrics** (STOMP); HTTP 200 on `/info` does not guarantee broadcasts succeed.

## 10. Common Misconceptions and Pitfalls

- **"With SockJS, we don't need to configure WebSocket on the proxy":** SockJS can rescue some networks via HTTP, but WebSocket may still be the primary transport and must support Upgrade for optimal performance.
- **"WebSocket got 101 so SockJS polling works too":** polling separately depends on POST, buffering, cookies, CORS, timeouts, and sticky sessions.
- **"SockJS fallback definitely solves corporate proxies":** proxies may also block long-lived HTTP requests or specific POSTs; there is no universal guarantee.
- **"`/topic/x` is an NGINX route":** it is a STOMP destination, not an HTTP endpoint.
- **"SockJS `server-id` automatically pins to the backend":** it is just a URL segment; the LB must be explicitly configured with routing rules.
- **"The simple broker works in a cluster":** the in-memory broker does not distribute subscriptions across instances; a cluster needs an external broker architecture.
- **"A SockJS `h` heartbeat always fires every 25 seconds":** negotiated STOMP heartbeats can supersede SockJS heartbeats.
- **"Enabling CORS `*` solves auth":** credentialed cross-origin requests have strict rules; wildcards cause browser rejections and widen attack surfaces.
- **"Disabling all CSRF for SockJS":** exempt only specific HTTP endpoints when genuinely needed, while keeping STOMP CONNECT properly protected.
- **"Assuming every old browser uses iframes":** allowed origins and X-Frame-Options/CSP can disable iframe transports.
- **"No need to test real clients":** a Java unit test will not catch browser mixed-content, CSP, cookies, CDN, iframes, or proxy buffering issues.
- **"Reconnect automatically replays messages":** it only creates a new connection; you must re-subscribe and handle missed messages per business contract.

## 11. Production Deployment Checklist

Before enabling SockJS in production, explicitly document *why* fallbacks are needed and which browsers/networks are supported; test native WebSocket in the target environment before adding complexity.

Verify the entire chain: `/ws/info` and all SockJS transport paths are neither rewritten nor blocked; NGINX forwards WebSocket Upgrade cleanly, disables buffering for streaming, defines timeouts based on real heartbeats, and enforces affinity across multiple application nodes. Ensure HTTPS/WSS schemes, Origin/CORS/CSRF/cookies/auth, frame-options, and CSP match security policy.

Test both transport paths through the **public hostname**, measure reconnect/fallback behavior, test node failures, and test session refreshes. Declare deployment successful only when clients receive **real STOMP MESSAGEs** over both WebSocket and HTTP polling; an HTTP 200 from `/info` is necessary but not sufficient.

## 12. References

- Spring Framework Reference — SockJS Fallback: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/fallback.html
- Spring Framework Reference — Enable STOMP: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/enable.html
- Spring Framework 6.1 Javadoc — SockJsServiceRegistration: https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/web/socket/config/annotation/SockJsServiceRegistration.html
- Spring Security Reference — WebSocket Security, SockJS & CSRF: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- NGINX official docs — ngx_http_proxy_module: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- StompJS guide — Using STOMP with SockJS: https://stomp-js.github.io/guide/stompjs/rx-stomp/ng2-stompjs/using-stomp-with-sockjs
- SockJS protocol definitions — HTTP paths and frame semantics: https://github.com/sockjs/sockjs-protocol
