# Deploying Spring Web Behind a Reverse Proxy: HTTPS, Forwarded Headers, Streaming, and WebSocket

## 1. Deployment picture and commonly confused failures

In production deployments, users typically connect to a **reverse proxy** (Nginx, Envoy, gateway, ingress, load balancer), which forwards requests to a Spring application running on an internal network. The proxy can terminate TLS and alter protocol, IP address, hostname, port, path prefix, and data-transfer characteristics.

```text
Browser / API client
https://app.example.test       wss://app.example.test/ws
          │ TLS to proxy
          ▼
┌──────────────────────────────────────────────┐
│ Reverse proxy / Load balancer                 │
│ - HTTPS certificate, TLS policy               │
│ - route, trust boundary, forwarded headers    │
│ - HTTP buffering/timeout, WebSocket Upgrade   │
└──────────────────────────────────────────────┘
          │ Internal HTTP/1.1 (example)
          │ Controlled Host/Forwarded/X-Forwarded-*
          ▼
Spring Boot / Spring MVC or WebFlux
http://127.0.0.1:8080
          │
          ├─ REST/redirect/absolute link
          ├─ SSE/NDJSON/file streaming
          └─ WebSocket handler / STOMP endpoint
```

An application behind a proxy may see the internal request as `http://127.0.0.1:8080`, even though the real client used HTTPS. Without passing and handling original metadata properly, the application may return:
- `Location: http://...` instead of `https://...`, causing mixed content, redirect loops, or broken OAuth callbacks.
- Cookies missing `Secure`, or wrong URL/scheme/host inferred from the request.
- SSE "waiting a long time and arriving all at once" due to buffering/compression at the proxy.
- WebSocket handshakes failing (`400`/`404`/`426`/`502`) or connections dropping due to missing Upgrade or idle timeouts.
- Wrong client IP logs, or worse: trusting IP/host headers forged by an attacker.

No single Spring flag fixes all of these. You must align **TLS & trust boundary → forwarded metadata → buffering/timeouts → WebSocket routing → end-to-end tests**.

The examples use **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+, and Nginx**, with specific notes for Servlet MVC/WebFlux. Hostnames, network addresses, and certificate paths are shown to illustrate the model; real deployments use your system's domains, certificates, internal networks, and security policies.

## 2. HTTPS termination: two distinct connections

**TLS termination at the proxy** means client TLS is authenticated/terminated at the proxy, after which the proxy can open an unencrypted HTTP connection **over a controlled internal network** to Spring.

```text
Browser -- HTTPS/TLS --> Nginx -- HTTP --> Spring :8080
```

Advantages: centralizes certificates, TLS versions/ciphers, HSTS, and certificate lifecycle; Spring only needs to listen on an internal port. From Spring's viewpoint, however, `request.getScheme()` and `isSecure()` initially reflect the **internal hop** (HTTP, false), not the browser's protocol. Proxy-verified metadata such as `X-Forwarded-Proto: https` or `Forwarded: proto=https;host=...` is required.

**End-to-end TLS / re-encryption** uses HTTPS on proxy → backend as well:

```text
Browser -- HTTPS/TLS --> Proxy -- HTTPS/TLS --> Spring
```

Here the proxy must verify the upstream certificate/hostname when configured this way; enabling upstream HTTPS without properly verifying server identity does not protect against backend spoofing. Consider mTLS when the network/architecture requires it. Forwarded headers remain useful because external hostname/port/public prefix may differ from internal ones even when both hops use HTTPS.

**Do not just turn on `server.ssl.*` in Spring and assume the proxy is set:** if the proxy terminates TLS while upstream switches to HTTPS, `proxy_pass` must match the backend protocol/port. A mismatch typically triggers `502 Bad Gateway` or TLS handshake errors. Do not enable HTTPS on the backend solely because clients use HTTPS if the topology places TLS termination at the trust boundary.

Core proxy responsibilities:
1. Redirect HTTP port 80 to HTTPS port 443 if required by the system.
2. Use a valid certificate for the public hostname; configure modern TLS and automated renewal.
3. Block direct Internet access to the application port; the backend must only accept traffic from trusted proxies/ingress.
4. Enforce request size, connection, and appropriate security policies; align proxy timeouts with the workload.
5. Emit complete public scheme/host/port metadata under a clear policy, and never forward forged external values.

HSTS (`Strict-Transport-Security`) should only be enabled after confirming HTTPS works reliably across target domains/subdomains, especially if using `includeSubDomains`. Session cookies generally need `Secure`, `HttpOnly`, and `SameSite` per auth/cross-site policy; forwarded scheme informs the app when setting them, though it does not replace cookie configuration.

## 3. Forwarded headers: restoring real URLs and defining the trust boundary

Two common header families:

**RFC 7239 `Forwarded`:**

```http
Forwarded: for=203.0.113.10;proto=https;host=app.example.test
```

**`X-Forwarded-*` (de facto):**

```http
X-Forwarded-For: 203.0.113.10
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
```

Some proxies also send `X-Forwarded-Prefix: /portal` when the public path has a prefix that differs from the app. The example address `203.0.113.0/24` and domain `example.test` belong to documentation space, not real reachable endpoints.

Meaning of each field:
- `For` / `X-Forwarded-For`: client IP at the start of the proxy chain (possibly multi-hop).
- `Proto` / `X-Forwarded-Proto`: externally visible protocol, e.g., `https`.
- `Host` / `X-Forwarded-Host`: public hostname, sometimes with port.
- `X-Forwarded-Port`: public port if used by the proxy.
- `X-Forwarded-Prefix`: public base path when the proxy strips/rewrites prefixes.

Once trusted and processed by the framework, request-based operations such as building absolute links, redirects, `getScheme()`, `getServerName()`, and `isSecure()` can reflect the client-facing URL. Distinguish:
- The upstream HTTP request's `Host` header set by the proxy.
- Forwarded headers managed by the proxy.
- `request.getRemoteAddr()` at the socket may still be the proxy's address, not the original IP; extracting the real IP across proxies depends on the container/adapter and trust model.

### The most important security rule

**Never trust `Forwarded`/`X-Forwarded-*` supplied by an Internet client.** If an attacker sends:

```http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: http
```

and the application trusts it directly, absolute redirects or password-reset URLs can point to the wrong host, or cookie/URL security can be compromised. At the **trusted edge proxy**, you must:
1. Clear/overwrite both `Forwarded` **and** all incoming `X-Forwarded-*` headers from outside, even unused ones.
2. Rewrite fresh values controlled by the proxy from the trusted connection (validated hostname, actual client IP, TLS state).
3. Prevent external callers from bypassing the proxy to hit the backend directly.
4. With multiple proxy layers, define exact trusted hops/networks; do not infer the real IP by blindly taking the first element of `X-Forwarded-For` from any source.

**`X-Forwarded-For` in Nginx:** `$proxy_add_x_forwarded_for` *appends* the client address to an existing `X-Forwarded-For` header. If Nginx is an **Internet-facing edge proxy** and does not strip incoming headers, appending can preserve spoofed values. The Nginx example below uses `X-Forwarded-For $remote_addr` to **overwrite** any browser-supplied chain. If Nginx sits behind a trusted CDN/LB, configure the trust chain via `real_ip_header`/`set_real_ip_from` or platform mechanisms before reconstructing the IP, rather than assuming `$remote_addr` is always the browser IP.

## 4. Spring Boot: NATIVE, FRAMEWORK, and NONE

Spring Boot 3.3 supports:

```yaml
server:
  forward-headers-strategy: framework
```

Available values:

| Strategy | Mechanism | Notes |
| --- | --- | --- |
| `none` | Do not process forwarded metadata via Boot strategy | Use when there is no trusted reverse proxy or metadata should not be trusted |
| `native` | Use underlying web server/container support (Tomcat, Jetty, Reactor Netty per stack) | Header support and behavior depend on the container |
| `framework` | Use Spring Framework's handler | Servlet MVC uses `ForwardedHeaderFilter`; reactive WebFlux uses `ForwardedHeaderTransformer` |

Certain cloud platforms detected by Boot may default to `native`; other environments typically default to `none`. **Declare it explicitly** so deployments are easy to review. `framework` is often helpful when you want consistent Spring handling of public prefixes and URLs/redirects; `native` fits when infrastructure already relies on container-specific remote-IP/trust logic. Avoid letting **both the container and the framework filter interpret the same header set** without verification.

**Servlet MVC:** `ForwardedHeaderFilter` reads/applies metadata for requests and certain response operations like `sendRedirect`. It has `setRemoveOnly(true)` when you only want to strip forged headers without **applying** metadata.

**WebFlux:** `ForwardedHeaderTransformer` processes metadata before Spring creates the exchange for handlers; it has a similar `setRemoveOnly(true)`. Spring Boot auto-configures these under `server.forward-headers-strategy=framework`; if registering beans/filters manually, avoid duplicate processing. These classes **do not authenticate the proxy**: enforcing the trust boundary at the ingress/network layer remains mandatory.

### Checking path prefixes and absolute URLs

Suppose the public path is `https://app.example.test/portal/api/orders` while Nginx strips `/portal` before forwarding `/api/orders`. Setting only `X-Forwarded-Proto` without the public prefix can cause generated links to omit `/portal`. Choose **one** consistent model:
- The proxy preserves `/portal` so the backend knows the application context path, or
- The proxy strips the prefix and supplies `X-Forwarded-Prefix: /portal` under trusted config, with matching framework version and context support.

Test each configuration with an endpoint that builds URLs and with real redirects/`Location`. Never hardcode public URLs in every controller just to work around a broken forwarded-header policy. For an application served at the root path like the example below, `X-Forwarded-Prefix` is **not needed**.

### Tomcat redirect context root

With Spring MVC on Tomcat, when terminating SSL at a proxy with a context path, Spring Boot documentation notes `server.tomcat.redirect-context-root=false` so `X-Forwarded-Proto` is evaluated before the container redirects to append `/`. Apply this only when actually using Tomcat/context-root redirects, not universally.

## 5. Nginx: HTTPS, header sanitization, streaming, and WebSocket Upgrade

Example Nginx config for an **edge reverse proxy** accepting public TLS with upstream Spring listening on HTTP at `127.0.0.1:8080` on the same host. This is a reference config; replace `app.example.test` and certificate paths with real infrastructure. `proxy_read_timeout` is the **idle gap without receiving bytes** from upstream, not a total response deadline.

```nginx
# Place inside http { ... }.
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    server_name app.example.test;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.test;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        # Trust only metadata generated by the edge proxy.
        proxy_set_header Host $host;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Ssl "";
        proxy_set_header X-Forwarded-Prefix "";

        # WebSocket: hop-by-hop headers must be forwarded explicitly.
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        proxy_connect_timeout 5s;
        proxy_send_timeout 75s;
        proxy_read_timeout 75s;

        # Regular responses may be buffered by default.
        # The SSE endpoint in the example returns X-Accel-Buffering: no.
    }
}
```

**Do not copy verbatim without reviewing trust/network/TLS:** real certificates must exist and match the host, firewalls must block direct client bypass to the backend, Nginx must accept only allowed hosts, and extra policies are needed behind another CDN/ingress. If `proxy_set_header Host $host` is insufficient for apps using custom public ports, define the proper host/port policy. Nginx behavior varies by version; HTTP/2 on the client side does not automatically mean upstream WebSockets use HTTP/2. The snippet uses the **HTTP/1.1 Upgrade** path to the backend.

### WebSocket requires Upgrade/Connection

`Upgrade` and `Connection` are hop-by-hop headers: HTTP proxies normally do not forward them to backends unless explicitly configured. To establish a WebSocket tunnel through a reverse proxy, the client sends an HTTP/1.1 handshake with `Upgrade: websocket`; upstream replies `101 Switching Protocols`; the proxy maintains a long-lived bidirectional tunnel.

Key directives:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
proxy_read_timeout 75s;
```

In `map`: requests carrying `Upgrade` set `Connection: upgrade`, while others set `Connection: close` per official Nginx examples (not optimal for upstream keep-alive on every normal request, though clear and easy to learn from). In other HTTP/1.1 setups, you can tune keep-alive and routing for normal requests as long as WebSocket handshakes remain intact.

**Keeping connections alive:** Nginx closes an idle tunnel if upstream sends nothing for `proxy_read_timeout` (Nginx docs commonly default to 60 seconds). Increase the read idle timeout or have the backend send ping/pong/WebSocket heartbeats frequently enough to avoid proxy idle closure. `proxy_read_timeout=75s` does not mean every WebSocket connection dies after 75 seconds; with timely traffic, connections can stay open long-term.

**STOMP over WebSocket:** beyond the tunnel, the broker/app needs proper heartbeats, session cleanup, and subscription management. Replacing raw `/ws` with a STOMP handshake endpoint does not fundamentally alter proxy rules; SockJS fallbacks also use HTTP polling/streaming paths, so route all corresponding paths if SockJS is enabled.

### Buffered SSE/streaming

Nginx proxy buffering (usually enabled by default) can collect upstream data before flushing to the browser per buffer policy, preventing `EventSource`/`curl -N` from seeing events immediately. For specific endpoints, you can:

- Disable proxy buffering in `location /events`: `proxy_buffering off;`, or
- Have the application return `X-Accel-Buffering: no` on the SSE response so Nginx does not buffer that response (provided `proxy_ignore_headers` is not ignoring it). The example below takes this approach.
- Check gzip/Brotli or compression at proxy/CDN layers, as they can also hold data before flushing.
- Ensure the controller **flushes** events to the actual response with `text/event-stream` content type and sends heartbeat comments for long streams.

Do not turn off buffering globally across the whole API if only a few streaming endpoints need low latency; doing so can alter proxy throughput and memory behavior. With multiple proxy/CDN layers, disable buffering at **every layer involved**; changing one Nginx does not guarantee an upstream CDN streams chunks immediately.

## 6. Runnable Spring Boot example: scheme, redirect, SSE, and WebSocket

We build a small Spring MVC app, sending traffic **directly to localhost HTTP** during development, then running behind Nginx HTTPS per section 5. Endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /diag` | Shows scheme, host, secure flag, and URL seen by Spring after forwarded processing |
| `GET /go` | Redirects to absolute URL `/status` to verify `Location` |
| `GET /status` | Simple target for redirect |
| `GET /events` | Emits 3 SSE events, flushed via `SseEmitter`, setting `X-Accel-Buffering: no` |
| `GET /ws` Upgrade | Raw WebSocket echo to verify `101 Switching Protocols` and bidirectional frames |

Structure:

```text
reverse-proxy-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/ProxyDemoApplication.java
    └── resources/application.yml
```

**`settings.gradle`**

```groovy
rootProject.name = 'reverse-proxy-demo'
```

**`build.gradle`** — Java 17+, Gradle 8.x:

```groovy
plugins {
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'java'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
}
```

**`src/main/resources/application.yml`**

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
```

Only enable reading forwarded headers when a **trusted proxy boundary** actually exists. If a dev server is exposed publicly, any client calling `localhost:8080` directly via port forwarding/NAT could forge headers; this is why backends must be bound to internal networks or firewalled against non-proxy access.

**`src/main/java/demo/ProxyDemoApplication.java`**

```java
package demo;

import java.io.IOException;
import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@SpringBootApplication
public class ProxyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxyDemoApplication.class, args);
    }

    @Bean("sseTaskExecutor")
    ThreadPoolTaskExecutor sseTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("demo-sse-");
        return executor;
    }
}

@RestController
class DemoController {
    private final TaskExecutor taskExecutor;

    DemoController(@Qualifier("sseTaskExecutor") TaskExecutor taskExecutor) {
        this.taskExecutor = taskExecutor;
    }

    @GetMapping("/diag")
    Map<String, Object> diag(HttpServletRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("scheme", request.getScheme());
        result.put("secure", request.isSecure());
        result.put("host", request.getServerName());
        result.put("port", request.getServerPort());
        result.put("url", request.getRequestURL().toString());
        return result;
    }

    @GetMapping("/status")
    Map<String, String> status() {
        return Map.of("status", "ok");
    }

    @GetMapping("/go")
    ResponseEntity<Void> redirect() {
        URI target = ServletUriComponentsBuilder
            .fromCurrentContextPath()
            .path("/status")
            .build()
            .toUri();
        return ResponseEntity.status(HttpStatus.FOUND)
            .location(target)
            .build();
    }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    SseEmitter events(HttpServletResponse response) {
        response.setHeader("X-Accel-Buffering", "no");
        SseEmitter emitter = new SseEmitter(30_000L);

        taskExecutor.execute(() -> {
            try {
                for (int i = 0; i < 3; i++) {
                    emitter.send(SseEmitter.event()
                        .id(Integer.toString(i))
                        .name("tick")
                        .data("event-" + i));
                    Thread.sleep(1_000);
                }
                emitter.complete();
            } catch (IOException disconnected) {
                // Client disconnected; container/Spring handles the I/O error.
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                emitter.complete();
            }
        });
        return emitter;
    }
}

@Configuration
@EnableWebSocket
class WebSocketConfig implements WebSocketConfigurer {

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(new EchoHandler(), "/ws");
        // Checks Origin for same-origin requests by default.
    }

    static final class EchoHandler extends TextWebSocketHandler {
        @Override
        protected void handleTextMessage(WebSocketSession session,
                                         TextMessage message) throws IOException {
            session.sendMessage(new TextMessage("echo: " + message.getPayload()));
        }
    }
}
```

**Explanation of points to verify:**
- `/diag` reads the request after `ForwardedHeaderFilter` (when valid headers exist and Boot strategy is `framework`), showing public scheme/host, though this endpoint should only be enabled in test environments or protected because it can expose topology.
- `/go` constructs an absolute `Location` from the restored request instead of hardcoding `http://localhost:8080`.
- `/events` returns an `SseEmitter` with `Content-Type: text/event-stream`, flushes events through Spring MVC, and sets `X-Accel-Buffering: no` so Nginx does not buffer this specific response. The finite 3-event loop simplifies testing; long-lived production SSE needs cleanup/heartbeats, listener management, and better threading. The small executor pool here is just for demo; with many concurrent streams, use non-blocking/scheduled fan-out rather than parking a thread per client indefinitely.
- `/ws` uses raw Spring WebSocket echo. In production, add authentication, authorization, protocol-appropriate Origin/CSRF checks, and concurrent-send policies; the sample only demonstrates the Upgrade transport.
- `@EnableWebSocket` requires `spring-boot-starter-websocket`, and Spring MVC's `SseEmitter` runs on Servlet async. Do not drop this Servlet code straight into a WebFlux/Netty-only application expecting it to compile.

Run locally:

```bash
gradle bootRun
```

Verify directly (on the server machine):

```bash
curl -i http://localhost:8080/status
curl -i http://localhost:8080/go
curl -N -i http://localhost:8080/events
curl -s http://localhost:8080/diag
```

**Expected local results without forwarded headers**:
- `/status`: HTTP 200, JSON containing `"status":"ok"`.
- `/go`: HTTP 302, `Location: http://localhost:8080/status` (host corresponds to the actual request URL).
- `/events`: status 200 and events `id:0`, `event:tick`, `data:event-0`, followed by events 1 and 2 roughly every 1 second before stream completion.
- `/diag`: `scheme` is `http`, `secure` false, host `localhost` or the actual request host.

These verification commands reflect expected behavior; raw HTTP transcripts vary with default headers and versions.

Once valid Nginx HTTPS is running on a real domain, call:

```bash
curl -i https://app.example.test/go
curl -N -i https://app.example.test/events
curl -s https://app.example.test/diag
```

`/diag` is expected to show `scheme=https`, `secure=true`, and the public host. `/go`'s `Location` must start with `https://app.example.test/`. With `curl -N`, all three events arrive incrementally rather than bunched at the end once proxy buffering is configured properly. `app.example.test` is an illustrative domain; replace it with a real DNS name and certificate.

### Testing WebSocket

In a browser open to a page on the same public origin:

```javascript
const socket = new WebSocket("wss://app.example.test/ws");
socket.onopen = () => socket.send("hello");
socket.onmessage = (event) => console.log(event.data);
socket.onerror = (error) => console.error(error);
socket.onclose = (event) => console.log("closed:", event.code);
```

With a properly configured real domain, the console receives `echo: hello`. DevTools Network → WS displays the `101 Switching Protocols` handshake and WebSocket frames. In local testing you can use `ws://localhost:8080/ws` from a same-origin local page; on an HTTPS page you must use `wss://` because browsers block `ws://` as mixed active content.

**Origin note:** browser WebSockets send an `Origin` header; Spring checks same-origin by default. When testing from a console on a different origin, the handshake may be rejected even when Nginx Upgrade is completely right. Do not fix it with `setAllowedOrigins("*")` in apps with authentication/sessions; verify the real public origin, cookie auth, and Origin policy.

## 7. Streaming in Servlet MVC vs. WebFlux: flush, heartbeat, backpressure

Both MVC and WebFlux can stream SSE/data, though their I/O models differ:

| Spring MVC Servlet | Spring WebFlux |
| --- | --- |
| `SseEmitter` / `ResponseBodyEmitter` / `StreamingResponseBody` | `Flux<ServerSentEvent<T>>` / `Flux<T>` / `DataBuffer` |
| Servlet async; response writes can block | Non-blocking model on an appropriate reactive server |
| Needs a production-ready `AsyncTaskExecutor` | Avoid blocking the event loop; use schedulers only when needed |
| Cleanup via `onCompletion`/`onTimeout`/`onError` on `SseEmitter` | Cleanup via `doFinally(SignalType.CANCEL)` / resource scope |
| Heartbeats help detect client disconnects on long HTTP connections | Same; cancel/transport errors reflect stream closure depending on network |

WebFlux example (**illustrative only**, do not paste into the MVC app in section 6):

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(10))
        .map(i -> ServerSentEvent.<String>builder()
            .id(Long.toString(i))
            .event("heartbeat")
            .data("tick-" + i)
            .build())
        .doFinally(signal -> log.info("SSE ended: {}", signal));
}
```

Requires imports `GetMapping`, `MediaType`, `ServerSentEvent`, `Flux`, `Duration`, and an app-declared logger; the snippet is not standalone. **Never call `block()` on the reactive event loop**. When the browser/user cancels or the proxy closes the stream, the publisher can receive cancellation. However, subscription cancellation is no promise that every network/socket closure occurs instantaneously across proxy layers.

**Heartbeat/flush:** a long-lived stream that emits no bytes for too long may be closed by Nginx, an LB, or a CDN due to `read idle timeout`. Emit periodic SSE comment pings (e.g., `: ping` followed by a blank line) or named heartbeat events per contract; the interval must be shorter than the idle timeout **with margin for jitter**. Do not send overly frequent heartbeats to hundreds of thousands of clients without evaluating CPU and bandwidth.

**Compression:** gzip/Brotli can increase buffering because encoders wait for enough data. For `text/event-stream`, inspect server/proxy/CDN settings; if low latency is required, exclude SSE from compression at any delaying layer.

**Chunked and HTTP/2:** streaming does not mean `Transfer-Encoding: chunked` must appear for every client. HTTP/2 does not use HTTP/1.1 chunked transfer coding; verify **event arrival timing and data framing** rather than relying on a single transport header.

**Resources and backpressure:** Spring can flush individual events, yet slow networks and many clients still create memory/backpressure/thread pressure. Cap active streams, publish rates, per-subscriber queues, payload sizes, and clean up resources. Never call `collectList` on an unbounded Flux. For large file downloads, stream data, monitor direct memory/heap, and cap download concurrency.

## 8. WebSocket/STOMP behind a proxy: lifecycle and scaling

A WebSocket begins with an HTTP handshake and upgrades to a long-lived connection. Requirements beyond basic proxying:

- **Forwarded public origin:** browsers use `wss://` matching HTTPS; the app checks Origin/auth/cookies and any redirect URLs.
- **Upgrade:** Nginx must forward `Upgrade`/`Connection` and speak HTTP/1.1 on the backend hop when protocol Upgrade applies.
- **Idle timeout:** `proxy_read_timeout` and ingress/LB timeouts must be sufficient or paired with ping/pong; do not confuse read timeout with total session lifetime.
- **Multi-instance scaling:** raw WebSocket sessions are pinned to the node holding the TCP connection. Load balancers must keep connections alive; reconnects may land on another node. With Spring's in-memory STOMP simple broker, subscriptions are not shared across nodes automatically; consider an external broker relay.
- **Authentication/sessions:** HTTPS termination does not replace WebSocket authentication. Browser WebSocket APIs do not permit arbitrary custom headers; design cookies or token/subprotocol/handshake flows securely. Avoid leaking uncontrolled bearer tokens in URLs/queries/logs.
- **SockJS fallback:** adds `/info` and XHR streaming/polling paths; proxy routing, CORS, buffering, and sticky-session requirements can differ from native WebSocket.
- **Connection closing:** close codes are not always received; on network drops, rely on heartbeats and idempotent cleanup. With STOMP, `SessionDisconnectEvent` can fire more than once.

`101 Switching Protocols` only proves the handshake/tunnel was established—**not** that business publishing/subscriptions/auth work. Send a test message, verify the reply, observe reconnect/timeout behavior, and test node draining during rolling updates.

## 9. Layer-by-layer verification checklist

| Check | How to run | Passing criteria |
| --- | --- | --- |
| TLS/certificate | `curl -I https://domain`, browser certificate inspector | Valid certificate, matching hostname, no HTTP downgrade |
| Redirect HTTP → HTTPS | `curl -I http://domain/path` | Public HTTPS `Location` preserving path/query, no loop |
| Scheme/host seen by Spring | Protected `/diag` endpoint | Correct `https`/public host/port after forwarded processing |
| Host spoofing | Verify proxy sanitizes `Forwarded` and all `X-Forwarded-*` | External clients cannot trick the app into generating spoofed-host URLs |
| SSE latency | `curl -N -i https://domain/events` measuring timestamps | Events arrive progressively, not batched at the end |
| SSE timeout | Idle below/above timeout with appropriate heartbeats | Connections do not drop unexpectedly |
| WebSocket Upgrade | Browser DevTools Network → WS | `101` handshake, bidirectional frames |
| WebSocket idle/reconnect | Drop network, close tab, retry | Server cleans up, client reconnects per policy |
| Multi-node | Test 2+ replicas behind load balancer | Routing/subscriptions and rolling restarts behave as expected |
| Resource use | Metrics, tracing, heap, active connections, queues | No stream/socket leaks; limits and cleanup enforced |

**Common troubleshooting:**

1. `502/504` from Nginx: wrong upstream host/port/protocol, backend unavailable, bad backend TLS, or request exceeded timeout; check Nginx error logs and Spring health.
2. OAuth redirect / `Location` reverts to HTTP: forwarded proto missing or ignored by Spring, or public prefix/host mishandled.
3. "Too many redirects": inconsistent HTTPS redirects across layers where the backend thinks requests remain HTTP; inspect CDN/LB/Nginx/Spring and trust config.
4. Internal host leaked in responses: app builds absolute URLs from the internal host; check forwarded host/port/prefix and reverse-proxy settings.
5. SSE returns all data in a batch: proxy buffering, compression, missing app flush, or CDN holding chunks.
6. SSE closes at exactly 60s idle: check `proxy_read_timeout` and heartbeat interval; timeout is idle gap without bytes, not max response duration.
7. WebSocket `400`/`426`: `Upgrade` or `Connection` header not forwarded, wrong HTTP version/hop, Origin/protocol mismatch.
8. WebSocket `403`: rejected by Origin/CORS/auth/security policy; do not disable policies blindly.
9. WebSocket `404`: wrong path/ingress prefix stripping, or backend did not register the handshake endpoint.
10. WebSocket `101` then closes quickly: proxy idle timeout, missing heartbeats, app exception, session/resource limits, or node restart.
11. Client IP in logs is the proxy: unconfigured trusted chain or web-server remote-IP behavior; never read raw unverified headers for IPs.
12. Many streams spike CPU/RAM: one blocking writer/thread per client, unbounded queues, huge payloads, missing cleanup, or closed connections with lingering listeners.

When debugging, correlate **request ID/trace ID** across proxy access logs, Spring logs, and client DevTools; record status, latency, upstream status, bytes sent, handshake errors, timeouts, and connection closes. Avoid logging cookies/Authorization/URLs with secrets, especially WebSocket handshake queries.

## 10. Production deployment principles

- **Single trusted source for public URLs:** domain/hostname validated at ingress; proxy generates forwarded metadata; Spring applies a consistent strategy.
- **Network isolation:** backends/private services accept connections only from trusted proxies; firewalls/security groups/network policies are primary defenses against forged forwarded headers.
- **Managed TLS lifecycle:** automated cert renewal, chain/hostname checks, key permissions, redirect policies, and upstream HTTPS if the threat model requires it.
- **Layered timeouts:** connect, send, read-idle, app async, broker/WebSocket heartbeats, and request/business deadlines are distinct clocks. Never use one number for all of them.
- **Bounded streaming:** disable buffering/compression only on endpoints needing low latency; maintain heartbeats and cleanup, and measure slow consumers.
- **Stateful WebSocket operations:** manage auth, Origin, subscriptions, idle handling, node draining, reconnects, graceful deployment, and session limits.
- **Test close to user behavior:** test directly through the public hostname and real proxy; unit/controller tests cannot validate TLS/headers/network streaming/Upgrade.
- **Never enable proxy trust unconditionally:** in staging/dev or when backends can be reached directly, attackers can inject forwarded headers without a trust boundary. Use `none` or `removeOnly` in unprotected environments.

## 11. Self-check questions

1. Browser calls HTTPS yet Spring returns `Location: http://localhost:8080/login`. What to check first? → Whether the proxy sends trusted `X-Forwarded-Proto/Host`, Spring sets the right `server.forward-headers-strategy`, and the backend is not accessed directly.
2. Why can `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for` be dangerous at the Internet edge? → It can append onto a client-forged value instead of replacing it with a trusted IP.
3. How do `framework` and `native` differ? → One uses Spring's `ForwardedHeaderFilter`/`Transformer`, while the other uses the container/network engine; avoid double-processing without checking.
4. SSE displays all three events together after three seconds even though the server sends one per second. Where to look? → Buffering/compression in Nginx/CDN or missing app flush, not just tweaking `SseEmitter`.
5. Does `proxy_read_timeout 75s` forbid WebSockets from running longer than 75s? → No. It is a read-idle interval; with traffic/heartbeats, connections stay open long-term.
6. WebSocket handshake returns `101`, yet no STOMP MESSAGE arrives. Does that prove the proxy is completely right? → No; check STOMP CONNECT/SUBSCRIBE, auth, broker routing, and event semantics.
7. With multi-replica deployments, do client reconnects automatically restore simple-broker subscriptions? → No; in-memory sessions and subscriptions must be re-established or backed by an appropriate broker architecture.
8. Why can't you trust `X-Forwarded-Host` directly from a browser? → Attackers can skew absolute URLs/redirects/cookie logic; a trusted proxy must sanitize it.
9. When `curl -N` receives events promptly while browsers do not, what else should be checked? → Browser caching/compression/CDN/EventSource parsing/response media type/CORS, plus every network layer.
10. When the proxy terminates TLS, is HTTP from proxy → backend always insecure? → It depends on network trust and threat model; if the internal hop needs protection, use verified upstream HTTPS or mTLS.

## 12. Official documentation

- Spring Boot 3.3 — Running Behind a Front-end Proxy Server: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server
- Spring Framework 6.x — Forwarded Headers (Servlet): https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers
- Spring Framework 6.x — Forwarded Headers (WebFlux): https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html#webflux-forwarded-headers
- Spring Framework 6.x — Asynchronous Requests, SSE, disconnects: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework 6.x — WebSocket Handshake: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
- Nginx — WebSocket proxying: https://nginx.org/en/docs/http/websocket.html
- Nginx — proxy buffering, `X-Accel-Buffering`, and `proxy_read_timeout`: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239
