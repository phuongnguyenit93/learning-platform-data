# Allowed Origins, Reverse Proxy Deployment, and TLS

WebSocket creates a long-lived, bidirectional connection between the browser and the server. In a production environment, the connection usually passes through a reverse proxy or load balancer, while the website is served over HTTPS. The Spring application needs to control the origin at the handshake step, the proxy must forward the protocol upgrade request, and TLS must be configured consistently from the browser to the security termination point.

These three parts each have their own role:

- **Allowed origins** restrict which websites are allowed to initiate a WebSocket from the browser.
- **The reverse proxy** forwards the HTTP Upgrade to the application and passes the original host/protocol information.
- **TLS** encrypts the connection over the network; when the website runs over HTTPS, the browser needs to use `wss://`.

This lesson focuses on Spring Framework on the Servlet stack, `WebSocketConfigurer` configuration, the NGINX reverse proxy, and a runnable Java 17 application to test the handshake.

## 1. The WebSocket Handshake and Origin

WebSocket starts with an HTTP request asking the server to upgrade the protocol:

~~~http
GET /ws/echo HTTP/1.1
Host: app.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example.com
~~~

If the server accepts the handshake, it returns `101 Switching Protocols`. From that point on, the TCP connection is kept open for both sides to send and receive WebSocket frames.

`Origin` describes the origin of the page that initiated the connection. An origin consists of a scheme, host, and port:

- `https://app.example.com`
- `https://admin.example.com`
- `http://localhost:8080`

Path does not belong to the origin. `https://app.example.com/app` and `https://app.example.com/other` have the same origin. Changing the scheme, hostname, or port creates a different origin.

### Why Must Origin Be Checked?

Browsers automatically send cookies or authentication credentials attached to a website when creating a connection. If an external website can open a WebSocket to a logged-in user's application, that website can abuse the login session to send commands or read data. This situation is commonly called Cross-Site WebSocket Hijacking.

WebSocket is not protected by the Same-Origin Policy in the same way that JavaScript access to ordinary HTTP resources is protected. Therefore, the server must check the handshake's `Origin`.

By default, Spring WebSocket accepts only same-origin requests. You can expand the list for another valid frontend, but you should keep the list specific and intentional.

Checking Origin mainly protects browser clients. A native program or script that crafts HTTP requests itself can set the `Origin` header on its own; therefore, Origin is not a user authentication mechanism. The application still has to authenticate identity and authorize WebSocket operations.

## 2. Configuring Allowed Origins in Spring

With a raw WebSocket handler, implement `WebSocketConfigurer` and call `setAllowedOrigins()` on the endpoint registration:

~~~java
@Configuration
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final WebSocketHandler echoHandler;

    public WebSocketConfiguration(WebSocketHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/echo")
                .setAllowedOrigins(
                        "https://app.example.com",
                        "https://admin.example.com"
                );
    }
}
~~~

Browsers from the two declared origins can initiate the handshake. Other origins are rejected before the WebSocket session is established.

### setAllowedOrigins and setAllowedOriginPatterns

`setAllowedOrigins(...)` accepts a list of specific origins. This is the easiest option to control for production:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .setAllowedOrigins("https://app.example.com");
~~~

`setAllowedOriginPatterns(...)` supports patterns when many subdomains need to be allowed:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .setAllowedOriginPatterns("https://*.example.com");
~~~

`setAllowedOriginPatterns` has been available since Spring Framework 5.3.5. Patterns need to be restricted to domains controlled by the organization.

If multiple environments are needed, put the origin list into configuration by profile or environment variable. Example:

~~~properties
app.websocket.allowed-origins=https://app.example.com,https://admin.example.com
~~~

You can read the property using the Spring Environment:

~~~java
public WebSocketConfiguration(
        EchoHandler echoHandler,
        Environment environment) {

    this.echoHandler = echoHandler;
    this.allowedOrigins = environment.getRequiredProperty(
            "app.websocket.allowed-origins", String[].class);
}
~~~

Then pass this array into `setAllowedOrigins(allowedOrigins)`. For local development, you can override it to `http://localhost:8080`. Do not put localhost into the production allowlist without a specific requirement.

Spring lets you configure `*` to accept every origin. This is convenient for testing, but very broad for applications with cookies or login sessions. Do not use it as the production default. If combined with CORS/SockJS credentials, the wildcard `*` is incompatible with `allowCredentials=true`.

## 3. How Allowed Origins Differ from CORS

Both CORS and WebSocket origin validation involve the `Origin` header, but they are not the same mechanism.

The WebSocket handshake is an HTTP Upgrade request. Browsers do not perform a normal CORS preflight before opening a WebSocket. Spring checks `Origin` during the handshake through the origin handshake interceptor.

With SockJS, in addition to the WebSocket transport, XHR streaming or polling fallbacks may be used. These HTTP transports may need CORS response headers. Spring SockJS automatically adds the necessary headers if no other CORS configuration is already handling the request.

Therefore:

- Configuring CORS for a REST API does not automatically replace `setAllowedOrigins` on a WebSocket endpoint.
- Configuring allowed origins for WebSocket does not mean every REST endpoint has CORS configured.
- If using SockJS, check allowed origins, CORS headers, and Spring Security's frame policy together.

When restricting allowed origins for SockJS, some iframe-based transports that cannot check the origin will be disabled. This is a limitation to take into account if very old browsers must be supported.

## 4. Applying to a STOMP Endpoint

If the application uses STOMP over WebSocket instead of a raw WebSocket handler, allowed origins are configured on the STOMP endpoint:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

The client connects to `/ws`, and then exchanges STOMP frames over WebSocket. The origin check still happens at the handshake. Access rights to destinations and messages need to be controlled at the STOMP/Spring Security layer.

If using Spring Security with STOMP, configure user authentication and message destination authorization. Spring Security has a CSRF mechanism for STOMP CONNECT; the client needs to send the CSRF token per the configuration. Allowed origins do not replace authentication, CSRF protection, or authorization.

With raw WebSocket, authentication is usually performed during the HTTP handshake using a session/cookie or an appropriate authentication mechanism. After the connection is established, the handler must still check whether the user has permission to perform the action sent in the message.

## 5. The Reverse Proxy Must Forward the WebSocket Upgrade

In a common deployment, the browser connects to NGINX or a load balancer on the HTTPS port. The proxy forwards the request to Spring Boot running on an internal port.

~~~text
Browser
  |
  | wss://app.example.com/ws/echo
  | TLS + HTTP Upgrade
  v
NGINX reverse proxy :443
  |
  | HTTP/1.1 Upgrade
  | internal network
  v
Spring application :8080
  |
  v
WebSocketHandler
~~~

HTTP `Upgrade` and `Connection` are hop-by-hop headers. A reverse proxy does not automatically forward them like ordinary headers. The proxy must be configured to forward them explicitly so that the backend server knows the client wants to upgrade the protocol.

A successful handshake usually has a `101 Switching Protocols` response. If the proxy does not forward Upgrade, the application may return 400/404/426 or the connection may be closed before WebSocket is established.

## 6. Configuring NGINX for WebSocket

Suppose the public hostname is `app.example.com`, NGINX listens on HTTPS at port 443, Spring Boot listens on internal HTTP at `127.0.0.1:8080`, and the endpoint is `/ws/echo`. TLS is terminated at NGINX.

Put `map` in the `http` block of the NGINX configuration:

~~~nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
~~~

Server configuration:

~~~nginx
upstream spring_websocket_backend {
    server 127.0.0.1:8080;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/letsencrypt/live/app.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.example.com/privkey.pem;

    location /ws/ {
        proxy_pass http://spring_websocket_backend;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $remote_addr;

        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
~~~

`map` produces the appropriate Connection value when a request does or does not have Upgrade. If there is only a WebSocket endpoint, configuring `Connection "upgrade"` directly can also work; using map is easier to reuse when a location handles multiple types of requests.

Important directives:

- `proxy_pass` forwards the request to the Spring application.
- `proxy_http_version 1.1` uses HTTP/1.1 for the upstream handshake.
- `proxy_set_header Upgrade` forwards the WebSocket upgrade request.
- `proxy_set_header Connection` forwards the upgrade intent.
- `proxy_set_header Host` preserves the public hostname.
- `X-Forwarded-Proto` indicates whether the client connected to the proxy via HTTP or HTTPS.
- `X-Forwarded-Port` indicates the public port the client used.
- `X-Forwarded-For` forwards the client address information according to the proxy policy.
- `proxy_read_timeout` limits how long NGINX waits for data from the upstream.

By default, NGINX closes a proxied connection if the upstream does not send data for 60 seconds. For a WebSocket with few messages, increase `proxy_read_timeout` or configure heartbeat/ping to keep the connection alive and detect dead connections.

`proxy_pass` in the example does not append a URI after the hostname, so the `/ws/echo` path is preserved when forwarded to the upstream. If the proxy changes the prefix, check the rewrite rules so Spring receives the exact endpoint mapping.

### Note on X-Forwarded-For

The example uses `$remote_addr` because it assumes NGINX is the direct edge proxy. If there is also a trusted load balancer in front of NGINX, configure trusted proxies and how the client address chain is built appropriately. Do not blindly preserve arbitrary `X-Forwarded-For` values sent by an external client and treat them as a trusted identity.

The browser's `Origin` header needs to be preserved for Spring to check. Do not replace `Origin` with `Host` or `X-Forwarded-Host`; they represent different information.

## 7. Forwarded Headers in Spring

When TLS terminates at the proxy, the request from the proxy to Spring may be internal HTTP even though the browser uses HTTPS. If the application only sees the internal request, it may see the `http` scheme, port `8080`, and the internal host. The actual user accesses `https://app.example.com`.

This difference affects absolute URLs, redirects, secure-cookie logic, and same-origin checks in some situations.

Spring provides `ForwardedHeaderFilter` to read `Forwarded` or `X-Forwarded-*`, and then wraps the request/response so that they reflect the host, port, and scheme from the client's perspective.

With a Spring Boot Servlet application, you can register the filter as a bean:

~~~java
@Bean
public ForwardedHeaderFilter forwardedHeaderFilter() {
    return new ForwardedHeaderFilter();
}
~~~

If you register the filter yourself in the Servlet container, place the filter early before any filters that need to read the adjusted scheme, host, or port.

Spring Boot also has the `server.forward-headers-strategy` option. Choose `framework` if you want to use Spring's `ForwardedHeaderFilter`, or `native` if the container/server already has a corresponding handling mechanism. Do not enable multiple mechanisms handling the same set of headers without understanding their order and outcome.

### Trust Boundary of Forwarded Headers

The application cannot tell on its own whether `Forwarded` or `X-Forwarded-*` headers come from a trusted proxy or were forged by a client. The edge proxy must strip forwarded headers sent in by external clients and write the standard values itself.

Only enable forwarded header processing when the application receives requests solely from a trusted proxy or when the network already has a proxy verification mechanism. If the backend can still be accessed directly from the Internet, a client can forge the scheme/host/port that the application trusts.

`ForwardedHeaderFilter` has a `removeOnly` mode if you want to strip forwarded headers from the request without using them to alter the request wrapper. Choose the mode suited to the proxy architecture.

## 8. TLS: ws:// and wss://

WebSocket has two schemes:

- `ws://` is WebSocket without TLS encryption.
- `wss://` is WebSocket running over TLS.

If the website is loaded over HTTPS, the browser should connect the WebSocket using `wss://`. An HTTPS page opening `ws://` may be blocked by the browser as mixed content.

JavaScript example:

~~~javascript
const socket = new WebSocket("wss://app.example.com/ws/echo");

socket.addEventListener("open", () => {
    console.log("WebSocket connected");
    socket.send("hello");
});

socket.addEventListener("message", (event) => {
    console.log("Server:", event.data);
});

socket.addEventListener("close", (event) => {
    console.log("WebSocket closed:", event.code, event.reason);
});

socket.addEventListener("error", (event) => {
    console.error("WebSocket error", event);
});
~~~

`Origin` in the handshake is still the page's origin, for example `https://app.example.com`. Do not put `wss://app.example.com` into allowed origins; an allowed origin is the HTTP origin consisting of the page's scheme, host, and port.

### TLS Termination at the Reverse Proxy

This is the common model:

1. The browser creates a TLS connection to NGINX using `wss://`.
2. NGINX verifies the certificate and decrypts the connection.
3. NGINX forwards the WebSocket over the internal network to Spring using HTTP Upgrade.
4. Spring processes WebSocket frames.
5. NGINX forwards frames in both directions over the TLS connection already open with the browser.

When using this model, the public certificate is installed on the proxy; the Spring backend should listen only on the internal network or a non-public interface; the firewall allows only the proxy to access the backend; the proxy sends the right forwarded headers; the client always uses `wss://` on the public side.

TLS termination at the proxy means the proxy-to-backend leg is not encrypted with TLS in this example. Place the backend in a private network and restrict access. If you need to encrypt the internal leg as well, configure TLS re-encryption: the proxy uses HTTPS to the backend and verifies the backend certificate.

### Direct TLS at Spring

You can also configure the Servlet container or embedded server to receive TLS directly. With Spring Boot, an example keystore configuration:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:server.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=KEYSTORE_PASSWORD_FROM_ENV
~~~

In a real configuration, set the password using an environment variable or secret manager; do not store secrets directly in committed configuration files. The keystore needs to contain a certificate and private key matching the hostname.

If placing a reverse proxy in front of a TLS-enabled backend, NGINX needs to use `proxy_pass https://...` and configure upstream certificate verification. Do not disable certificate verification in production just to work around trust errors.

## 9. Timeouts and Heartbeats for Long-Lived Connections

An ordinary HTTP request ends after the server returns a response. WebSocket keeps a connection open for a long time, so timeouts on proxies, load balancers, firewalls, and NATs can close the connection when there is no traffic.

NGINX `proxy_read_timeout` defaults to 60 seconds between reads of data from the upstream. This is not an absolute maximum duration of the WebSocket session. If the server sends data periodically, the timer is refreshed.

The connection can be kept alive using:

- WebSocket Ping/Pong frames at the protocol layer.
- STOMP heart-beat if using STOMP.
- Application-layer heartbeat messages if appropriate.
- Proxy/load balancer timeouts long enough relative to the heartbeat period.

The browser JavaScript WebSocket API does not provide a direct method to send a Ping control frame. The server or a WebSocket library can manage ping/pong. With STOMP, both sides can negotiate heart-beat in STOMP CONNECT/CONNECTED.

Do not simply raise timeouts to several hours and skip heartbeats. Heartbeats help detect dead connections and release sessions and server resources sooner.

## 10. Reverse Proxy, Load Balancing, and Multiple Instances

After a successful handshake, a WebSocket connection is held on the same proxy tunnel to one backend throughout the connection's lifetime. A proxy cannot move an open TCP connection to another instance the way it balances short individual HTTP requests.

If there are multiple Spring instances:

- Each WebSocket connection is routed to one instance at handshake time.
- That connection continues to use the chosen instance until it closes.
- When the client reconnects, the proxy may choose a different instance.
- State stored only in the memory of one instance will not automatically appear on the new instance.

If the application uses the in-memory STOMP simple broker, subscription and routing data are scoped to each instance. When multiple nodes are needed, consider a STOMP broker relay or an appropriate shared state/message broker architecture.

Sticky sessions can help SockJS HTTP fallback requests go to the same instance, depending on the architecture. However, sticky sessions do not replace a shared broker or a state recovery mechanism when an instance fails.

## 11. SockJS When Deploying Behind a Proxy

SockJS adds fallback transports when WebSocket is unavailable. Fallback requests may be HTTP streaming or polling, so the proxy needs to handle ordinary HTTP requests alongside WebSocket Upgrade.

When deploying SockJS:

- The proxy must forward the exact path prefix of the SockJS endpoint.
- Configure timeouts appropriate for streaming/polling.
- If the proxy buffers responses, check the latency of the streaming transport; you may need to disable buffering on the SockJS location per deployment requirements.
- Spring can automatically add CORS headers for XHR transports if no other filter is already handling it.
- If allowed origins are restricted, some iframe-based fallback transports will be disabled.
- Check `X-Frame-Options` if the application actually uses an iframe-based transport; do not loosen clickjacking protection headers across the entire site casually.

If all modern clients support WebSocket, SockJS may not be needed. Enable fallback only when there is a specific compatibility requirement.

## 12. Securing WebSocket Connections

A successful handshake only proves that the server accepted the connection at the start. It does not by itself guarantee that every subsequent message is valid.

Protection layers need to work together:

**Origin allowlist:** restricts which websites are allowed to initiate a connection from a browser.

**Authentication:** identifies the user from a session/cookie, OAuth2 access token, or appropriate authentication mechanism. Do not treat `Origin` as an identity.

**Authorization:** checks whether the user has permission to subscribe, publish, or invoke the corresponding action. With STOMP, authorize destinations and message types; with raw WebSocket, check permissions in the handler/service.

**CSRF:** if using cookie-based authentication, assess the risk of Cross-Site WebSocket Hijacking. With STOMP and Spring Security, configure CSRF tokens for CONNECT according to the security guidance.

**TLS:** use `wss://` for public traffic, and manage certificates, private keys, and renewal cycles.

**Proxy trust:** trust forwarded headers only when written by the edge proxy. Block direct access to the backend if the design requires every request to pass through the proxy.

**Resource limits:** limit message size, number of connections, send rate, idle time, and outbound queues to avoid one client consuming excessive resources.

## 13. Complete Example: Spring Boot WebSocket Echo

The example uses Java 17, Spring Boot 3.4.4, and `spring-boot-starter-websocket`. The application creates a raw WebSocket endpoint `/ws/echo`, accepts only the origin configured in the property `app.websocket.allowed-origins`, and echoes back the content the client sends.

Structure:

~~~text
websocket-origin-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── WebSocketApplication.java
        │       ├── WebSocketConfiguration.java
        │       └── EchoHandler.java
        └── resources/
            └── application.properties
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>websocket-origin-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.4</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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

### src/main/java/demo/WebSocketApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketApplication.class, args);
    }
}
~~~

### src/main/java/demo/EchoHandler.java

~~~java
package demo;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class EchoHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws Exception {

        session.sendMessage(
                new TextMessage("echo: " + message.getPayload()));
    }
}
~~~

### src/main/java/demo/WebSocketConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoHandler echoHandler;
    private final String[] allowedOrigins;

    public WebSocketConfiguration(
            EchoHandler echoHandler,
            Environment environment) {

        this.echoHandler = echoHandler;
        this.allowedOrigins = environment.getRequiredProperty(
                "app.websocket.allowed-origins", String[].class);
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/echo")
                .setAllowedOrigins(allowedOrigins);
    }
}
~~~

### src/main/resources/application.properties

~~~properties
server.port=8080
app.websocket.allowed-origins=https://app.example.com
~~~

Run the application:

~~~shell
mvn spring-boot:run
~~~

To test locally, override the origin with:

~~~shell
mvn spring-boot:run -Dspring-boot.run.arguments=--app.websocket.allowed-origins=http://localhost:8080
~~~

Open a web page from `http://localhost:8080` and run the JavaScript:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.addEventListener("open", () => {
    console.log("connected");
    socket.send("hello");
});

socket.addEventListener("message", (event) => {
    console.log(event.data);
});
~~~

Output in the browser console:

~~~text
connected
echo: hello
~~~

If you open the page from a different origin not in the allowlist, the handshake will be rejected. When deploying publicly behind NGINX with TLS, the client changes the URL to `wss://app.example.com/ws/echo` and configures the allowed origin to `https://app.example.com`.

This example confirms the Spring handler configuration and origin allowlist. To confirm the entire production path, you need to test the handshake through NGINX, a real certificate, forwarded headers, timeouts, and the deployment environment's authentication.

## 14. Diagnosing Common Errors

| Symptom | Common cause | How to check |
|---|---|---|
| HTTP 400/404/426 when opening WebSocket | Wrong path or proxy does not forward Upgrade | Check `Upgrade`, `Connection`, `proxy_http_version`, and endpoint mapping |
| HTTP 403 at handshake | Origin is not in allowlist or rejected by security filter | Check request `Origin`, allowed origins, and security logs |
| Works locally but fails through proxy | Wrong path rewrite, host, or forwarded headers | Compare public URL with upstream path and request metadata |
| Browser reports mixed content | HTTPS page is opening `ws://` | Use `wss://` |
| Connection closes automatically after about one minute | Proxy/load balancer idle timeout | Check `proxy_read_timeout` and heartbeat |
| Redirect or generated URL uses http | Application only sees internal scheme after TLS termination | Send forwarded headers and configure trusted forwarded header handling |
| SockJS polling works but WebSocket does not | Proxy only supports HTTP fallback, missing Upgrade forwarding | Check NGINX location and 101 handshake |
| Client connects but API calls are rejected | Authentication/authorization at message or HTTP layer is unsuitable | Check principal, token, CSRF, and destination authorization |
| Connection reconnects but loses subscription/state | Reconnected to another instance or state was only in local memory | Use a shared broker/state and design subscription recovery |

When diagnosing, look at the browser logs, the proxy access/error logs, and the Spring logs. A handshake passes through many layers; the status code at the proxy may differ from the backend's root error if the proxy rejects or times out on its own.

## 15. Production Deployment Checklist

- The endpoint is open only on the necessary paths.
- Allowed origins list the exact scheme, host, and port.
- Wildcard origin is not used for applications with sessions/credentials.
- Authentication and authorization are configured independently of Origin.
- STOMP CONNECT has CSRF protection when using Spring Security per the corresponding configuration.
- NGINX forwards `Upgrade` and `Connection`.
- Upstream uses HTTP/1.1 for the handshake per compatible configuration.
- `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and port reflect the public URL.
- The edge proxy strips untrusted forwarded headers from clients.
- The backend is accessible only from the proxy or permitted internal network.
- The certificate has the right hostname, is not expired, and is renewed automatically.
- Browsers use `wss://` when the website runs over HTTPS.
- Idle timeout and heartbeat are aligned between the proxy, load balancer, and application.
- SockJS fallback, CORS, and X-Frame-Options are tested if used.
- Concurrency, message size limits, rate limits, and connection counts have appropriate limits.
- Monitoring covers open session counts, handshake failures, close codes, idle timeouts, and reconnect rates.
- Tested through the exact public path, not just by calling the localhost backend directly.

## 16. Key Takeaways

- A WebSocket handshake starts with an HTTP Upgrade and succeeds when the server returns `101 Switching Protocols`.
- Spring WebSocket accepts only same-origin by default; use `setAllowedOrigins` or `setAllowedOriginPatterns` to expand in a controlled manner.
- An Origin consists of scheme, host, and port; it does not include path and does not use the `ws://`/`wss://` scheme.
- Origin validation mainly protects browsers; non-browser clients can spoof the header, so authentication and authorization are still needed.
- WebSocket origin validation differs from CORS; SockJS fallback may need CORS for XHR transports.
- The reverse proxy must forward `Upgrade` and `Connection` while preserving the exact path.
- TLS termination at NGINX allows clients to use `wss://` while the proxy forwards `ws://` on the internal network.
- `ForwardedHeaderFilter` helps Spring understand the public scheme/host/port, but only forwarded headers created by a trusted proxy may be trusted.
- WebSocket is a long-lived connection; configure timeouts and heartbeats for proxies/load balancers.
- When running multiple instances, a connection is tied to one backend throughout the session; state needs to be shared or recovered on reconnect.

## References

- [Spring Framework 6.2 — WebSocket Server Configuration and Allowed Origins](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/server.html)
- [Spring Framework 6.2 — WebSocket Overview and Handshake](https://docs.spring.io/spring-framework/reference/6.2/web/websocket.html)
- [Spring Framework 6.2 — SockJS Fallback and CORS](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/fallback.html)
- [Spring Framework 6.2 — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html)
- [Spring Security — WebSocket Same Origin and CSRF](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [NGINX — WebSocket Proxying](https://nginx.org/en/docs/http/websocket.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
