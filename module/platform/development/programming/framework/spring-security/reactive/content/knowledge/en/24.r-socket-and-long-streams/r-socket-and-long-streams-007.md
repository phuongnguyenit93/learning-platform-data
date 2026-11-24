# Protecting the WebSocket Handshake and Origin Checking

## 1. Why is the WebSocket handshake a security boundary?

WebSocket creates a bidirectional, long-lived channel between client and server. Before WebSocket frames begin, both sides perform an **HTTP handshake**; in standard HTTP/1.1 WebSocket, the browser sends a GET with headers `Upgrade: websocket`, `Connection: Upgrade`, `Sec-WebSocket-Key`, and typically `Origin`. The server authenticates, checks policy, and accepts or rejects the upgrade. On success, the standard response is **HTTP 101 Switching Protocols**.

```http
GET /ws/echo HTTP/1.1
Host: ws.example.invalid
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <random-key>
Sec-WebSocket-Version: 13
Origin: https://app.example.invalid
Cookie: SESSION=<browser-session-if-present>
```

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <server-computed-value>
```

This is **illustrative HTTP/1.1**, not a literal request sequence to replay verbatim; connections using HTTP/2 extended CONNECT have a different handshake. Once upgraded to WebSocket, messages **do not pass through an independent HTTP request/response cycle** per frame, so `SecurityWebFilterChain` does not automatically re-execute for each message.

**Topic:** Protecting the WebSocket handshake and Origin checking.  
**Parent context:** RSocket and long streams.  
**Module:** Spring Security - reactive.  
**Example versions:** Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Spring Security 6.5.x.

### Learning outcomes

1. Understand the layers of WebSocket handshake, security authentication, Origin validation, and frame authorization.
2. Recognize **Cross-Site WebSocket Hijacking (CSWSH)** when browsers automatically attach cookies to a WebSocket endpoint.
3. Understand why browsers **do not automatically enforce Same-Origin Policy to block WebSocket** the way CORS restricts reading `fetch` HTTP responses.
4. Validate `Origin` server-side using an **exact scheme + host + port allowlist**; distinguish `Origin` `https://app.example.invalid` from target WebSocket `wss://ws.example.invalid`.
5. Use `SecurityWebFilterChain` to require authentication/roles during the HTTP handshake before upgrading.
6. Apply a `WebFilter` to block invalid, missing, `null`, or mismatched Origins; understand that WebFlux `WebSocketHandler`/`SimpleUrlHandlerMapping` supports `CorsConfigurationSource`.
7. Never treat Origin as an authentication mechanism: non-browser clients can spoof Origin themselves.
8. Distinguish how browsers use HttpOnly session cookies from how non-browser clients add Authorization headers; do not carelessly put Bearer tokens into query params or subprotocols.
9. Build a Java 17+ WebFlux example with strict Origin guard, authentication, and an echo socket, plus HTTP + WebSocket handshake tests.
10. Enforce per-message permissions, timeouts, quotas, lifecycle, re-auth on token expiration, and long-lived connection management.
11. Relate to RSocket-over-WebSocket: same HTTP/Origin boundary, yet **RSocket SETUP/route security differs** from raw WebSocket frames.
12. Review TLS/WSS, proxies, load balancers, trusted forwarded headers, CORS/CSRF, and observability.

**Example limitations:** `ws://127.0.0.1` and demo credentials are strictly for localhost environments. Production must use `wss://` with TLS and proper authentication mechanisms. Domain `example.invalid` in this document is an example domain with no real service.

## 2. Security flow from HTTP to WebSocket

```text
Browser at Origin https://app.example.invalid
             |
             | new WebSocket("wss://ws.example.invalid/ws/echo")
             |
             | GET /ws/echo + Upgrade + Origin + Cookie (if any)
             v
WebFlux Server
  1. Ingress/TLS/proxy: route only to trusted backend
  2. Origin guard: origin must be in allowlist
  3. Spring Security SecurityWebFilterChain:
       extract Authentication from Basic/Bearer/WebSession...
       require authenticated/role/scope
  4. HandlerMapping + WebSocketHandlerAdapter
  5. WebSocketService/RequestUpgradeStrategy:
       validate handshake and upgrade
             |
             +-- reject -> HTTP 400/401/403 (depending on layer)
             |
             +-- accept -> HTTP 101, WebSocketSession
                               |
                               v
                      Application WebSocketHandler
                      each inbound frame:
                        - validate message type/size/schema
                        - authorize action/resource
                        - enforce tenant/owner/quotas
                        - control backpressure/lifetime
```

**Two stages do not replace each other:**
- **Handshake** decides whether the client may open the channel at connection time.
- **Message-level policy** decides inside the open channel whether the client may subscribe to a room, access a tenant, issue a command, or view data at each point in time.

Origin identifies **the web page source where the browser is running**, not who the user is. Session cookies/JWT/mTLS are separate mechanisms. HTTP 101 only proves the handshake was accepted, not permission to perform all subsequent actions.

### 2.1. What is the Origin header actually?

For a page at `https://app.example.invalid/chat` opening a WebSocket to `wss://ws.example.invalid/stream`, the header is typically:

```http
Origin: https://app.example.invalid
```

Not:

```http
Origin: wss://ws.example.invalid/stream
```

An Origin consists of **scheme + host + port**, with no URL path/query/fragment. When a website runs over HTTPS, Origin has `https://`; for a local frontend `http://localhost:3000`, Origin has `http://` even if the target is `ws://localhost:8080`. A `null` value can appear in some opaque origins (sandboxes, file URLs); **do not permit it by default** when endpoints carry sessions/credentials.

These Origins are all distinct:

```text
https://app.example.invalid             trusted production page
https://app.example.invalid:443         explicit port; policy must define
http://app.example.invalid              downgrade, not the same origin
https://evil.example.invalid            different host
https://app.example.invalid.evil.invalid  spoofed suffix
https://app.example.invalid:444         different port
null                                    opaque origin, reject per policy
```

Configure allowed origins explicitly, usually a small server-managed set. **Never** check `contains("app.example.invalid")`, `endsWith("example.invalid")`, or arbitrarily enable `*` for cookie-authenticated endpoints.

### 2.2. Why Browser Same-Origin Policy is not enough

For `fetch`, browsers regulate cross-origin access via CORS; with the **WebSocket API**, a browser can send a cross-origin handshake carrying `Origin`, while **the server** is responsible for rejecting Origins outside the allowlist. Never expect the browser to block the request solely because the attacker page has a different origin.

A CSWSH scenario:

1. User is logged into `https://ws.example.invalid` with a session cookie.
2. User opens `https://attacker.example.invalid`.
3. Attacker page JavaScript runs `new WebSocket("wss://ws.example.invalid/ws/account")`.
4. If the browser sends the cookie and the server trusts the cookie without **checking Origin**, a connection can be established on the user's behalf.
5. The attacker can send/receive frames and execute actions permitted to the user.

Whether cookies are sent depends on `SameSite`, `Secure`, browser context, and current policies; **do not treat `SameSite` as the sole defense**. Certain browsers/configurations/session models can still produce cross-site credentialed requests. The server must check Origin.

### 2.3. Origin is not authentication

A CLI/non-browser client can set:

```http
Origin: https://app.example.invalid
```

even though it is not running from that page. Therefore an Origin allowlist is a **browser cross-site defense**, not identity proof. You must authenticate users/services via session/Bearer/mTLS/trusted client certificates and authorize independently.

If the app has machine clients needing to connect without Origin, create a **separate endpoint/policy**, using mTLS/JWT and network controls. Never widen a cookie-authenticated endpoint into "missing Origin = trusted client," as attackers can use non-browser tools or proxies.

## 3. How does Spring WebFlux handle the handshake?

### 3.1. Raw WebSocket in Spring Framework

Key WebFlux classes:

| Component | Role |
|---|---|
| `WebSocketHandler` | Handles `WebSocketSession` and inbound/outbound messages |
| `WebSocketSession` | `receive()`/`send()`, `handshakeInfo`, close status |
| `SimpleUrlHandlerMapping` | Maps URL `/ws/echo` to `WebSocketHandler` |
| `WebSocketHandlerAdapter` | Connects `HandlerMapping` with `WebSocketService` |
| `HandshakeWebSocketService` | Performs basic HTTP handshake checks and uses `RequestUpgradeStrategy` |
| `RequestUpgradeStrategy` | Performs upgrade for Reactor Netty/Tomcat/Jetty |
| `CorsConfigurationSource` (reactive) | Configures origins for `WebSocketHandler` |
| `WebFilter` | Intercepts requests at the HTTP layer before handler/upgrade |
| `SecurityWebFilterChain` | Authentication/authorization at the HTTP handshake |
| `ReactiveSecurityContextHolder` | Security Context for reactive execution |
| `HandshakeInfo` | Handshake headers, URI, principal, and metadata |

Spring Framework WebFlux documentation instructs having `WebSocketHandler` implement `org.springframework.web.cors.reactive.CorsConfigurationSource` or configuring `corsConfigurations` on `SimpleUrlHandlerMapping`. This is the **reactive stack** API; do not copy **Servlet**'s `OriginHandshakeInterceptor` from `org.springframework.web.socket.server.support` into WebFlux raw WebSocket.

Servlet WebSocket docs mention `WebSocketHandlerRegistration#setAllowedOrigins(...)`. That is **not** a method you call directly on reactive `HandshakeWebSocketService`. Avoid confusing Servlet `WebSocketHandler` with `org.springframework.web.reactive.socket.WebSocketHandler`.

### 3.2. HandlerMapping CORS config and Origin guard

WebFlux `HandlerMapping` supports CORS; WebSocket docs suggest providing `CorsConfigurationSource` on the handler. Some HTTP/CORS handling depends on mapping and handshake details, so the demo uses **two clear layers**:

1. `WebSocketHandler` implements `CorsConfigurationSource` for Spring Framework, listing finite origins.
2. `WebFilter` runs before authentication/upgrade steps, **self-rejecting** invalid Origins fail-closed on browser-credentialed endpoints.

This is not a mandate that every app must write two identical layers; the goal is to demonstrate a **testable Origin policy** that does not rely on browser-side CORS response headers. Whether using one or two layers, you need real **HTTP Upgrade** integration tests.

### 3.3. When is HTTP authentication applied?

A `SecurityWebFilterChain` can use:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/ws/echo").authenticated()
    .anyExchange().denyAll())
```

This is a snippet that belongs inside Security config. Before accepting the handshake, Spring Security processes the HTTP request and `Authentication` is established via the configured mechanism. An HTTP 401 or 403 prevents the upgrade; the request never becomes a `WebSocketSession`.

For WebFlux raw `WebSocketHandler`, handshake authentication **does not automatically turn into an authorization engine for every text/binary frame**. If a frame carries `joinRoom("tenant-b")` or `deleteDocument("id")`, the handler/service must verify permissions for the operation/resource, avoiding treating user-supplied destination/tenant as authorization.

### 3.4. Session cookie vs. Bearer token

**Browser using native WebSocket API**:

```javascript
// Browser page running at https://app.example.invalid
const socket = new WebSocket("wss://ws.example.invalid/ws/echo");

socket.onopen = () => socket.send("ping");
socket.onmessage = event => console.log(event.data);
socket.onclose = event => console.log(event.code);
```

The browser sets handshake headers per API rules. Native `new WebSocket(url[, protocols])` **does not let JavaScript set an arbitrary `Authorization` HTTP header**. For browser SSO, the usual choice is `HttpOnly`/`Secure`/`SameSite` cookies with server-side session auth. In that case, Origin checking becomes even more critical.

**Non-browser clients** can supply HTTP Basic or Bearer headers during the handshake. The runnable demo in section 8 uses HTTP Basic only to demonstrate Origin + authentication ordering, never treating Basic as an optimal browser production protocol.

Other designs:
- Short-lived, one-time WebSocket tickets issued over HTTPS inside an authenticated session, bound to user/Origin/endpoint and consumed once. Replay/expiry must be managed and tickets never logged.
- Tokens via `Sec-WebSocket-Protocol` require valid protocol negotiation; never stuff long-lived access tokens into subprotocol headers/echo responses out of convenience.
- Access tokens in URL query parameters easily leak into proxy/access logs/history/traces; avoid them.
- When browsers log in via cookies, CSRF protection for HTTP login or unsafe requests is still required. Spring Security's default CSRF focuses on unsafe HTTP methods; a GET WebSocket upgrade **is not automatically protected by a CSRF token**.
- `SameSite` cookies, `HttpOnly`, `Secure`, and Origin are distinct layers; none replaces server-side authentication.

## 4. Handshake boundary vs. message/connection lifecycle

### 4.1. Handshake only checks at time t0

```text
t0: Valid Bearer token/session -> WebSocket accepted
t1: subscription notifications/tenant-a -> check permissions
t2: user locked or token expired
t3: client continues sending frames
t4: logout/permission revoke
```

If validated only at t0, the open connection can still operate at t3. HTTP Security filters **do not re-run on every frame**. The application must decide:

- Maximum connection lifetime and idle timeout.
- On access token expiry/logout/revocation: close connection, require re-auth, or downgrade permissions; implement per threat model.
- For sensitive operations, check current permissions from a trusted authorization store or identity context.
- Should tenant/room membership changes take effect immediately?
- Buffer/queue/stream credits/backpressure and outbound fan-out quotas.
- Validate message schema and size before business processing.
- Emit data only to authorized tenants/subjects, never based on self-declared room names.

### 4.2. CSRF, CORS, and WebSocket are not identical

| Mechanism | What does it protect? | What does it NOT protect automatically? |
|---|---|---|
| CORS | Browser policy for cross-origin HTTP responses/preflight | Does not block raw WebSocket handshakes in all browsers |
| Origin allowlist | Cross-site browser WebSocket connection attempts | CLI clients spoofing Origin; per-message permission checks |
| CSRF token | Browsers with session cookies sending unsafe HTTP requests | GET Upgrade does not enforce CSRF by WebFlux default |
| Authentication | Principal at handshake | Post-connection permission changes / all frames |
| Message authorization | Permissions per event/route/resource | TLS, DoS, malformed handshake |
| HTTPS/WSS | Transport confidentiality/integrity | User permissions and trusted Origin |
| SameSite/HttpOnly cookie | Partially reduces credential exposure/CSRF | Does not replace strict Origin + authorization |
| mTLS | Workload or client identity | User/tenant/record permissions without separate policy |

**Cross-stack note:** Spring Security Servlet `@EnableWebSocketSecurity` and STOMP message brokers include authorization integration and typically require CSRF on STOMP CONNECT. Do not infer that raw Spring WebFlux `WebSocketHandler` behaves identically. RSocket uses `RSocketSecurity`, not STOMP.

### 4.3. Limits and backpressure

WebSockets are long-lived; attackers can:
- Open thousands of idle connections without sending data.
- Send huge frames or malformed binary payloads.
- Send messages at high rates requesting unbounded fan-out.
- Subscribe to many rooms or trigger CPU-heavy streams.
- Stop reading responses so server buffers grow.
- Send fragmented frames to exhaust memory or tie up parsers.

You need connection limits per identity/IP, idle timeouts, maximum lifetimes, size limits at gateway/server/`RequestUpgradeStrategy`, per-message validation, bounded queues, backpressure, cancellation, and rate quotas. `Flux` does not automatically guarantee safety against memory/transport exhaustion.

### 4.4. Multitenant subscriptions

An authenticated user in tenant `acme` must not simply send:

```json
{"action":"subscribe","tenant":"globex","channel":"private-events"}
```

and join `globex`. The backend must verify the tenant/requested resource against the verified principal/membership/ACL. If permissions change while the socket is open, revoke the subscription or close the connection. Never derive tenant from `Origin` or `X-Tenant` instead of trusted authorization.

## 5. Origin validation: pass/fail cases

Suppose the production endpoint accepts only page `https://app.example.invalid`, and dev accepts `http://localhost:3000`.

| Origin header | Expectation | Why |
|---|---|---|
| `https://app.example.invalid` | Allow if authenticated | Exact production browser origin |
| `http://localhost:3000` | Allow in dev config | Local frontend origin |
| `https://attacker.example.invalid` | Deny | Host not in allowlist |
| `https://app.example.invalid.attacker.invalid` | Deny | Suffix spoof |
| `http://app.example.invalid` | Deny | Scheme downgrade |
| `https://app.example.invalid:444` | Deny | Different port |
| `Origin: null` | Deny | Opaque origin outside policy |
| Missing Origin | Deny on browser demo endpoint | Do not implicitly trust non-browsers |
| Two Origin headers | Deny | Ambiguous/duplicate input |
| `https://app.example.invalid, https://evil.invalid` | Deny | Not a single valid Origin in allowlist |
| `https://app.example.invalid/path` | Deny | Origin does not include path |
| `ws://app.example.invalid` | Deny | Origin uses http/https, not ws |
| `https://app.example.invalid/` | Deny in strict string policy | Trailing slash is not part of allowlisted serialized Origin |

A production app can strictly normalize default ports/IDN and parsing to support diverse browser clients; **do not accidentally relax policy** during normalization. The simplest approach for a finite known set of origins is comparing **exact full Origin strings**.

### 5.1. Why not validate against request Host?

WebSocket `Host` is the **target server**, whereas Origin is the **page calling WebSocket**. If the target is `ws.example.invalid`, you cannot simply compare `Origin host == Host` to declare it safe; a legitimate frontend app may live at `app.example.invalid`. Conversely, if you use caller-spoofable `Host` or `X-Forwarded-Host` to "compute expected origin," an attacker can influence the policy.

Trusted proxies/reverse proxies must normalize/strip forwarded headers at the boundary, and the backend must use trusted config rather than deriving allowlists from arbitrary request headers.

### 5.2. Do not enable allowOrigins("*") for cookie WebSockets

With credentialed WebSockets, wildcard `*` easily defeats CSWSH protection. Standard CORS likewise forbids wildcard origins combined with `allowCredentials=true`. Use a fixed list of origins and review whenever adding tenant domains. If multiple tenant origins exist, build the allowlist from **trusted registration** and enforce that the socket's tenant matches the principal; never treat a raw Origin as self-asserted tenant proof.

## 6. Runnable Java 17+ project: OriginGuard + HTTP auth + WebSocket Echo

This is a Spring Boot 3.5.x, Spring Security 6.5.x, Spring WebFlux/Netty project. The demo uses Basic auth for the Java test client (not a browser pattern), a **strict Origin filter**, and a `WebSocketHandler` with reactive CORS configuration.

Structure:

```text
src/main/java/demo/ws/
  SecureWebSocketApplication.java
  SecurityConfig.java
  OriginGuardFilter.java
  EchoSocketHandler.java
  WebSocketRoutes.java
  HealthController.java
src/test/java/demo/ws/
  WebSocketHandshakeTests.java
```

### 6.1. Dependencies

Create a Gradle Groovy project with Spring Initializr, Java 17+, Spring Boot 3.5.x. The `dependencies` section of `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

This is the dependencies block, **not** the entire `build.gradle`. Keep plugins, repositories, Java toolchain, and Gradle wrapper generated by Spring Initializr. Do not add `spring-boot-starter-web` because the demo needs inbound **WebFlux**, not Servlet MVC.

### 6.2. SecureWebSocketApplication.java

```java
package demo.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecureWebSocketApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecureWebSocketApplication.class, args);
    }
}
```

### 6.3. OriginGuardFilter.java: fail-closed before upgrade

```java
package demo.ws;

import java.util.List;
import java.util.Set;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public final class OriginGuardFilter implements WebFilter {

    private static final Set<String> TRUSTED_ORIGINS = Set.of(
        "http://localhost:3000",
        "https://app.example.invalid");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String path = exchange.getRequest().getPath()
            .pathWithinApplication().value();

        if (!"/ws/echo".equals(path)) {
            return chain.filter(exchange);
        }

        List<String> origins = exchange.getRequest()
            .getHeaders().getOrEmpty(HttpHeaders.ORIGIN);

        if (origins.size() != 1
                || !TRUSTED_ORIGINS.contains(origins.get(0))) {
            exchange.getResponse().setStatusCode(
                HttpStatus.FORBIDDEN);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}
```

**Exact explanation:**

- The filter only affects the `/ws/echo` endpoint, leaving `/health` and other routes unaffected.
- `@Order(Ordered.HIGHEST_PRECEDENCE)` runs very early in the WebFlux filter chain, before HTTP security/handler mapping in the demo configuration.
- Only a single `Origin` header and exact Origin value are allowed. Missing Origin (including CLI) → 403; this is an **intentional policy** for a browser-facing endpoint, not a requirement that every WebSocket endpoint must do this.
- Invalid Origin → HTTP 403, skips `chain.filter(exchange)`, so it never reaches the handler or upgrades.
- Valid Origin → the request still must pass **authentication/authorization**; Origin does not grant 101 by itself.
- Never use `Host`/`Forwarded` or query params as allowed origins.
- When deployed under a context path or gateway rewrite, verify `pathWithinApplication()` on the request **actually reaching the service** and match rules accordingly.
- In production, allowed origins should come from trusted server config (separating dev/prod), never hardcoding insecure local origins alongside production.

### 6.4. SecurityConfig.java: blocking unauthenticated handshakes

```java
package demo.ws;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails user = User.withUsername("learner")
            .password(encoder.encode("study-pass"))
            .roles("WS")
            .build();

        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/ws/echo")
                    .hasRole("WS")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Distinguishing responsibilities:**

- `OriginGuardFilter` verifies the **browser page origin**, without granting permissions.
- `SecurityWebFilterChain` authenticates the user via demo HTTP Basic and requires `ROLE_WS` to open the socket.
- `PasswordEncoderFactories` creates an encoder prefixing `{bcrypt}` on hashed passwords (per Security version defaults); no plaintext is stored in `UserDetails`. Demo passwords are for testing only; **never deploy static credentials in production**.
- `.formLogin(...disable())` is only for the Basic/non-browser example, because native JS WebSocket API cannot proactively add an HTTP Basic Authorization header. Browser production should use login/session cookies or a designed token/ticket flow.
- GET handshakes do not require a CSRF token by Spring Security default because GET is a safe HTTP method; to prevent CSWSH you need **strict Origin** plus optionally a one-time connection ticket for sensitive operations.
- Never open `/ws/**.permitAll()` hoping `WebSocketHandler` will authenticate itself.
- If switching to cookie login, configure session security and HTTPS/`Secure`/`HttpOnly`/`SameSite` cookies, CSRF on login/unsafe HTTP operations, plus the Origin allowlist.

### 6.5. EchoSocketHandler.java: WebSocketHandler + reactive CORS config

```java
package demo.ws;

import java.util.List;

import org.springframework.http.HttpMethod;
import org.springframework.stereotype.Component;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public final class EchoSocketHandler
        implements WebSocketHandler, CorsConfigurationSource {

    private final CorsConfiguration corsConfiguration;

    public EchoSocketHandler() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
            "http://localhost:3000",
            "https://app.example.invalid"));
        cors.setAllowCredentials(true);
        cors.setAllowedMethods(List.of(HttpMethod.GET.name()));
        cors.setAllowedHeaders(List.of("*"));
        this.corsConfiguration = cors;
    }

    @Override
    public CorsConfiguration getCorsConfiguration(
            ServerWebExchange exchange) {
        return corsConfiguration;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.send(
            session.receive()
                .take(4)
                .filter(message ->
                    message.getType() == WebSocketMessage.Type.TEXT)
                .map(message -> session.textMessage(
                    "echo:" + message.getPayloadAsText()))
        );
    }
}
```

**Explanation:**

- `CorsConfigurationSource` here belongs to `org.springframework.web.cors.reactive`; it provides the origin allowlist to WebFlux `HandlerMapping` per Spring Framework mechanics.
- `setAllowCredentials(true)` pairs with **finite origins**, never wildcards. Though the demo uses HTTP Basic, this configuration also illustrates policy when integrating browser cookie sessions.
- `handle` echoes only **text frames**, at most four inbound messages in one demo session; this is not a chat-room permission system.
- Never call `subscribe()`/`block()` inside the handler; publishers are managed by WebFlux/WebSocket infrastructure.
- Binary frames are ignored, yet production needs frame size caps, schema validation, quotas, and clear close policies; simple `filter` does not replace data validation.
- `session.receive()` and `session.send()` are reactive streams. Handler completion terminates the `WebSocketSession` lifecycle per infrastructure rules.
- Never assume every message is allowed just because the user was authenticated at handshake. For sensitive actions, read the verified principal from the connection context and enforce authorization in the service.

### 6.6. WebSocketRoutes.java: mapping handler

```java
package demo.ws;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration
public class WebSocketRoutes {

    @Bean
    HandlerMapping webSocketMapping(EchoSocketHandler handler) {
        SimpleUrlHandlerMapping mapping =
            new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.of("/ws/echo", handler));
        mapping.setOrder(-1);
        return mapping;
    }
}
```

Spring WebFlux configuration in Spring Boot provides `WebSocketHandlerAdapter` supporting `WebSocketHandler`/`WebSocketService` by default; no custom Servlet handshake interceptor is needed. `SimpleUrlHandlerMapping` maps `/ws/echo` precisely to `EchoSocketHandler`.

In production, if multiple routes/mappings exist, apply strict Origin and authentication to **every WebSocket endpoint**, avoiding leaving another route unprotected.

### 6.7. HealthController.java

```java
package demo.ws;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class HealthController {
    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }
}
```

### 6.8. Running locally

From the project root, using Initializr's Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Test health:

```bash
curl -i http://localhost:8080/health
```

Expected HTTP 200, body `ok`. Responses may vary in header/charset details by server.

Test an invalid Origin (no WebSocket upgrade needed to see the pre-handshake filter reject):

```bash
curl -i -H "Origin: https://evil.example.invalid" \
  http://localhost:8080/ws/echo
```

Expected HTTP 403. With a valid Origin but missing Basic auth:

```bash
curl -i -H "Origin: http://localhost:3000" \
  http://localhost:8080/ws/echo
```

Expected HTTP 401 from Spring Security Basic auth (this request has no Upgrade yet). A **successful** WebSocket connection requires a WebSocket client sending proper handshake headers, Origin, and Authentication; tests in section 7 use `ReactorNettyWebSocketClient` to do that.

**Never** send demo passwords over remote `ws://` or public HTTP; production must only use WSS/TLS and managed credentials.

## 7. Automated testing of WebFlux and real WebSocket handshakes

`WebTestClient` is great for testing HTTP filter outcomes (403 Origin/401 auth), yet it **does not replace** a real WebSocket handshake. To test 101/Upgrade, use `ReactorNettyWebSocketClient` against `@SpringBootTest`'s random port.

The following tests run offline against loopback Netty, without an external Identity Provider. Basic credentials exist only inside the test process.

File `src/test/java/demo/ws/WebSocketHandshakeTests.java`:

```java
package demo.ws;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebSocketHandshakeTests {

    @LocalServerPort
    int port;

    @Autowired
    WebTestClient http;

    private URI socketUrl() {
        return URI.create(
            "ws://127.0.0.1:" + port + "/ws/echo");
    }

    private HttpHeaders headers(String origin) {
        HttpHeaders headers = new HttpHeaders();
        if (origin != null) {
            headers.setOrigin(origin);
        }
        headers.setBasicAuth("learner", "study-pass");
        return headers;
    }

    private Mono<Void> connect(HttpHeaders headers) {
        return new ReactorNettyWebSocketClient()
            .execute(socketUrl(), headers, session -> {
                AtomicReference<String> message =
                    new AtomicReference<>();

                Mono<Void> outgoing = session.send(
                    Mono.just(session.textMessage("ping")));
                Mono<Void> incoming = session.receive()
                    .next()
                    .doOnNext(frame ->
                        message.set(frame.getPayloadAsText()))
                    .then();

                return Mono.when(outgoing, incoming)
                    .doOnSuccess(ignored -> assertEquals(
                        "echo:ping", message.get()));
            });
    }

    @Test
    void healthIsPublic() {
        http.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void missingOriginRejectedBeforeHandler() {
        http.get().uri("/ws/echo")
            .headers(h -> h.setBasicAuth("learner", "study-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void evilOriginIsRejectedEvenWithBasicCredential() {
        http.get().uri("/ws/echo")
            .headers(h -> h.setBasicAuth("learner", "study-pass"))
            .header(HttpHeaders.ORIGIN,
                "https://evil.example.invalid")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void suffixSpoofingIsRejected() {
        http.get().uri("/ws/echo")
            .headers(h -> h.setBasicAuth("learner", "study-pass"))
            .header(HttpHeaders.ORIGIN,
                "https://app.example.invalid.evil.invalid")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void portMismatchIsRejected() {
        http.get().uri("/ws/echo")
            .headers(h -> h.setBasicAuth("learner", "study-pass"))
            .header(HttpHeaders.ORIGIN,
                "https://app.example.invalid:444")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void nullOriginIsRejected() {
        http.get().uri("/ws/echo")
            .headers(h -> h.setBasicAuth("learner", "study-pass"))
            .header(HttpHeaders.ORIGIN, "null")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validOriginWithoutAuthenticationIsUnauthorized() {
        http.get().uri("/ws/echo")
            .header(HttpHeaders.ORIGIN,
                "http://localhost:3000")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validOriginButBadCredentialIsUnauthorized() {
        http.get().uri("/ws/echo")
            .headers(h -> h.setBasicAuth("learner", "wrong"))
            .header(HttpHeaders.ORIGIN,
                "http://localhost:3000")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void allowedOriginAndAuthenticatedWebSocketCanExchangeText() {
        connect(headers("http://localhost:3000"))
            .block(Duration.ofSeconds(10));
    }

    @Test
    void untrustedOriginCausesActualHandshakeFailure() {
        assertThrows(Exception.class, () ->
            connect(headers("https://evil.example.invalid"))
                .block(Duration.ofSeconds(10)));
    }

    @Test
    void missingOriginCausesActualHandshakeFailure() {
        assertThrows(Exception.class, () ->
            connect(headers(null))
                .block(Duration.ofSeconds(10)));
    }
}
```

**11 test methods** covering:
- 1 public HTTP health test.
- 5 fail-closed HTTP Origin tests (missing, evil, spoof, port, null).
- 2 valid-Origin tests without auth or with wrong Basic auth → 401.
- 1 real WebSocket handshake test with valid Basic + Origin sending/receiving text `ping`/`echo:ping`.
- 2 real WebSocket upgrade tests with invalid or missing Origin → handshake error before any echo.

**Limitations:** Tests use a client able to craft Origin and Basic headers arbitrarily, unlike browser JS; therefore the success test proves the server-side allowlist and HTTP auth for a **non-browser test client**, not that browser session cookies/CSRF are implemented. The `assertThrows(Exception.class)` assertions intentionally avoid locking onto a Reactor Netty handshake exception type that may change across versions; during project development you can inspect detailed error status codes.

### 7.1. Run command

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Expected:** 11 test methods PASS on compatible project dependencies; this is **static QA** of content and APIs, not a claim that Gradle was executed in this workspace. If tests time out due to network/environment issues, diagnose server startup, port, WebSocket handshake status, and HTTP auth; never remove the Origin filter to "fix" tests.

### 7.2. Manual testing with WebSocket tools

A WebSocket CLI client can send Origin and Basic headers, e.g., from a tool supporting custom handshake headers. Do not use HTTP GET `curl` without Upgrade to conclude a WebSocket session was created. When debugging, log **sanitized Origin, path, reason code, and verified user ID**, never Cookies, Authorization, full tokens, or raw PII messages.

Browser JS (if corresponding session-based authentication is implemented):

```javascript
const ws = new WebSocket("wss://ws.example.invalid/ws/echo");
ws.onopen = () => ws.send("hello");
ws.onmessage = e => console.log(e.data);
ws.onclose = e => console.log(e.code, e.reason);
```

Native browser JS has no standard way to set `Authorization: Bearer ...` on the `WebSocket` constructor. Do not copy the backend Basic demo into production browser auth without designing a session/ticket protocol.

## 8. Upgrading to cookie-authenticated browser WebSockets

### 8.1. Recommended flow

```text
1. Browser HTTPS to login API
2. Login has CSRF protection (if cookie/session flow)
3. Server creates protected WebSession
4. Returns session cookie with appropriate Secure + HttpOnly + SameSite
5. Browser from https://app.example.invalid
   -> new WebSocket("wss://ws.example.invalid/ws/secure")
6. Browser may attach cookie per browser cookie policy
7. Server:
   - Exact Origin allowlist
   - Cookie session authentication
   - ROLE_WS / handshake permissions
   - Optional one-time WS ticket
8. HTTP 101 -> WebSocket connected
9. Each frame -> validate action/tenant/record permissions
10. Logout/revocation -> close/invalidate session/socket per policy
```

To use WebFlux form-login sessions instead of the Basic demo, add `.formLogin(Customizer.withDefaults())` and configure security/session policies, login form, and CSRF token handling. Verify that the `SESSION` cookie is sent by the browser to the WebSocket host per SameSite/domain/secure settings; if frontend and socket are cross-site, never blindly relax `SameSite=None`/`allowOrigins("*")` without a threat assessment.

**Never** treat Cookie presence alone as an authenticated user: the session must be server-verified, have TTL/rotation/session fixation protection, and avoid exposing session IDs. If browsers can keep sockets open after logout, proactively close/reauthorize them.

### 8.2. One-time handshake tickets for sensitive endpoints

For channels accepting financial commands or streaming PII, in addition to Origin and sessions you can use tickets:
1. Browser calls authenticated HTTPS POST `/api/ws-ticket` with CSRF protection.
2. Server issues a high-entropy opaque random ticket, very short TTL, bound to session, Origin, user, and endpoint.
3. Client sends the ticket via a designed handshake mechanism (e.g., controlled short-lived subprotocol token or another secure cookie).
4. Server consumes the ticket **once** before upgrading or before the first message; reject replay/expired/wrong session.
5. Never log tickets/secrets, never echo tickets in the `Sec-WebSocket-Protocol` response, and never place long-lived credentials in URL query parameters.
6. On timeout/revocation, close the connection.

This is an **architectural design**, not a built-in Spring Security WebFlux auto-feature. If using `Sec-WebSocket-Protocol`, the application must negotiate a valid protocol string; never shove a Bearer token into the subprotocol list without controlling browser/proxy logs.

### 8.3. Authn sessions must not remain valid forever

A connection opened at 10:00 might still be open at 11:00 after the HTTP session has expired. Policies needed:
- Hard maximum connection age.
- Idle timeouts and heartbeat ping/pong.
- Re-auth or re-authorization for sensitive messages.
- Server-initiated close on logout or tenant permission revocation.
- Quotas per principal/tenant/room.
- Session state storage/lookup across multiple replicas, plus routing/stickiness if needed.
- Never allow a user authorized to subscribe with `tenant=acme` to switch to `tenant=globex` via message payload.

## 9. RSocket over WebSocket: critical differences

**RSocket is not synonymous with raw text WebSocket.** RSocket is a multiplexed message/stream protocol with SETUP and multiple request interactions like request-response, request-stream, channel, and fire-and-forget. It can run over TCP or WebSocket as its transport.

Spring Boot can expose RSocket over WebSocket on WebFlux/Netty:

```yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
```

This is a snippet **for an app with `spring-boot-starter-rsocket` and WebFlux Netty**, not configuration for the echo WebSocket demo above. If choosing a standalone TCP server, the HTTP `Origin` header **does not exist** at all; use TLS/RSocket SETUP/security per protocol.

### 9.1. Boundaries with RSocket-over-WebSocket

```text
Browser Origin
    |
    v
HTTP GET Upgrade /rsocket  (WebSocket transport)
    |  Origin guard + HTTP access policy
    v
RSocket SETUP frame
    |  Authentication metadata / RSocketSecurity
    v
RSocket routes:
    |  authorizePayload / application ACL
    v
requestResponse / requestStream / requestChannel
    |  permissions per route/tenant
    v
Data
```

If you only attach the demo's `OriginGuardFilter` to `/ws/echo`, it **does not protect `/rsocket`**. When adding RSocket-over-WebSocket, apply the Origin policy to the **exact mapping path `/rsocket`** at the HTTP/server adapter layer and test real handshakes. RSocket route security is a separate layer; never assume a raw `WebSocketHandler` will receive/understand RSocket frames.

### 9.2. Spring Security RSocket

Spring Security Reactive provides `@EnableRSocketSecurity`, `RSocketSecurity`, and `PayloadSocketAcceptorInterceptor`/`SecuritySocketAcceptorInterceptor` for RSocket SETUP/route authorization.

Conceptual snippet per Spring Security API:

```java
@Configuration
@EnableRSocketSecurity
class RSocketRules {

    @Bean
    PayloadSocketAcceptorInterceptor authorization(
            RSocketSecurity rsocket) {
        return rsocket
            .authorizePayload(authorize -> authorize
                .setup().authenticated()
                .route("notifications.*").hasRole("VIEWER")
                .anyRequest().denyAll())
            .build();
    }
}
```

This is a **snippet** requiring imports, RSocket messaging/server setup, and application-supported authentication metadata. You cannot paste it directly into a project with only `starter-webflux` and expect an RSocket server to appear automatically. When RSocket Security auto-config is present, Spring Boot can attach the interceptor to the server; test against the specific transport/mapping.

**Complementary roles:**
- **HTTP handshake Origin**: is the browser allowed to open the transport from this website?
- **RSocket SETUP authentication**: who is the RSocket requester?
- **RSocket route authorization**: are `notifications.private` or this tenant/channel allowed to be used?
- **Long-lived streams**: how are subscriptions cancelled/closed when scope/tenant permissions are revoked?

When using RSocket TCP, there is **no WebSocket HTTP handshake** or Origin policy; replace them with TLS/workload identity, authentication metadata, and RSocket authorization.

### 9.3. Differences from Spring STOMP WebSocket Security

Spring Security Servlet `@EnableWebSocketSecurity` and STOMP docs define rules on `MESSAGE`/`SUBSCRIBE` and STOMP CONNECT CSRF. Do not apply Servlet STOMP's `MessageMatcherDelegatingAuthorizationManager` directly to raw WebFlux `WebSocketHandler` or RSocket routes.

| Stack | Handshake | Message security |
|---|---|---|
| Spring WebFlux raw WebSocketHandler | `WebFilter`, `SecurityWebFilterChain`, reactive CORS/Origin policy | Application `WebSocketHandler`/service ACL |
| Spring MVC + STOMP broker | Servlet Security + WebSocket endpoint allowed origins | Spring Security Messaging/STOMP CONNECT/SUBSCRIBE rules |
| Spring RSocket over WebSocket | WebSocket transport Origin/HTTP policy (if integrated) | RSocket SETUP/route authorization + business ACL |
| Spring RSocket TCP | No HTTP Origin | TLS/RSocket SETUP/route policy |

Confusing these APIs often leads developers to believe a Servlet annotation will automatically protect a WebFlux/RSocket endpoint when in fact it is never invoked.

## 10. Reverse proxies, Cloud Gateways, and Origin

A deployment may look like:

```text
Browser https://app.example.invalid
   |
   | wss://ws.example.invalid/ws/echo
   v
Cloud Load Balancer / API Gateway
   | TLS termination / trusted proxy forwarding
   v
Spring Boot WebFlux /ws/echo
```

Checkpoints:

1. External WSS must have valid certificates; never use public `ws://`.
2. Gateways must support Upgrade/Connection and proper timeouts/idle heartbeats.
3. Gateways must forward or normalize `Origin` per policy; never rewrite Origin arbitrarily to bypass backend checks.
4. If Spring Security relies on `WebSession` cookies, check proxy cookie `Domain`/`Secure`/`SameSite`/`Path`.
5. Strip untrusted `X-Forwarded-Host`/`X-Forwarded-Proto` and trust only known proxies; never derive allowed origins from unverified forwarded headers.
6. Check all paths routing to the same backend to prevent alternative URLs or direct ingress from bypassing the Origin filter.
7. Never forward raw Bearer tokens to arbitrary upstreams; if the gateway performs OAuth2 token relay, enforce destination/audience policies.
8. Rate-limit handshake attempts/connection counts and active duration per identity.
9. WebSocket app instances need a shared session/revocation policy to revoke sessions across replicas.
10. Tracing/log redaction: log only handshake outcomes/normalized Origin/route/verified principal ID, never Cookie/Authorization/CSRF tickets.
11. If the socket path undergoes prefix rewriting, the Origin filter must match the actual backend path, not just the public URL.
12. For HTTP/2 WebSocket/extended CONNECT or special proxies, test the real transport rather than assuming HTTP/1.1 GET/101 logic applies everywhere.

**Host Header and Origin have distinct roles:** `Host` is where the request is sent, `Origin` is the page source; trusted routing/tenant identity must never rely on raw caller-controlled headers.

## 11. Common deployment mistakes

| Symptom | Cause | Fix |
|---|---|---|
| User opens attacker page and still connects via cookie | Server does not validate Origin | Strict allowlist, deny cross-site WebSocket handshakes |
| Gateway authenticated yet socket receives all events | Checked authn only at handshake | Message-level scope/tenant/record ACL |
| HTTP CORS is right yet WebSocket gets hijacked | Assumed browser CORS enforcement covers WS | Test real Origin validation on the server |
| Origin is `wss://app...` and gets rejected | Misunderstood Origin format | Origin header uses `http(s)` page origin |
| `Origin: null` is allowed | Overly permissive policy | Reject opaque origins unless explicitly designed |
| Non-browser can spoof Origin | Treated Origin as user identity | Mandate independent authn, never rely on Origin |
| `new WebSocket` does not send Authorization header | Browser API forbids custom auth headers | Use HttpOnly session cookies/ticket flow |
| Token leaked in WS URL `?token=...` | Token appears in proxy logs/analytics | Avoid URL tokens; use secure auth design |
| Code calls Servlet `OriginHandshakeInterceptor` | Confused Spring MVC and WebFlux | Use reactive `CorsConfigurationSource`/`WebFilter` |
| HTTP GET 200 interpreted as WebSocket connected | No Upgrade handshake | Use a real WebSocket client and verify 101 |
| WebSocket opened before logout still receives data | Authn only at t0 | Connection expiry/revocation/permission rechecks |
| Connections never close after inactivity | Missing idle timeout/heartbeat | Configure transport and session lifecycle |
| Attacker sends binary/oversized frames | Missing size/type validation | Max frame length, schema, rate quotas |
| `allowOrigins("*")` with credentials | Does not restrict cross-site browsers | Strict origins, proper `allowCredentials` policy |
| Cross-tenant subscription reads other data | Trusted message tenant from caller | Verified tenant + resource membership/ACL |
| RSocket-over-WS still lacks Origin policy | Guard only matches raw `/ws/echo` | Apply dedicated policy at RSocket mapping `/rsocket` |
| Used Servlet STOMP `@EnableWebSocketSecurity` for raw WebFlux | Wrong stack | WebFlux security + application frame ACL |
| TLS terminated at proxy but backend trusts any Host | Untrusted forwarded headers | Trusted proxies/fixed config, never derive allowlist from input |
| Unit tests pass, production has CSWSH | Forgot handshake tests from evil Origin with cookie | Browser/Netty handshake integration tests |
| Auto-closes right after 1 message | Publisher lifecycle code completed | Design receive/send lifecycle and quotas clearly |
| Logs contain session cookies/tokens | Debugged raw handshake headers | Redact; audit policy metadata only |
| Client retries continuously on 403 | Failed to distinguish Origin mismatch | Log reason category; never relax allowlist automatically |
| `SameSite` cookie treated as sufficient | Browser cookie policy varies by context | Origin + CSRF/session security + message ACL |

## 12. Exercises and answers

### Exercise 1 — Why must Origin be checked on the server?

**Answer:** Native browser WebSocket can connect cross-origin; the browser sends `Origin` but does not block all cross-site WebSockets like CORS `fetch`. The server must reject Origins outside the allowlist to prevent CSWSH.

### Exercise 2 — What is the Origin of `https://app.example.invalid/chat`?

**Answer:** `https://app.example.invalid`, without path. When that page opens `wss://ws.example.invalid/ws`, Origin remains the page origin, not `wss://...`.

### Exercise 3 — Can an attacker use a non-browser client with a spoofed Origin?

**Answer:** Yes. Origin is not authentication. Clients/users must be authenticated using trusted credentials/sessions/JWT/mTLS.

### Exercise 4 — The gateway already authenticated the session; does the handler need per-event permissions?

**Answer:** Yes. Handshake is only entry authorization. Message payloads may require permissions per room/tenant/operation, and permissions can be revoked while the connection stays open.

### Exercise 5 — Why is the default CSRF filter not enough for WS?

**Answer:** WebSocket HTTP/1.1 handshake is a GET, and Spring Security's default CSRF focuses on unsafe HTTP methods. Raw WebFlux WS does not automatically enforce STOMP CONNECT CSRF. Strict Origin and optionally one-time tickets are needed.

### Exercise 6 — Should Origin `*` be allowed when using session cookies?

**Answer:** No. A cross-site page can use session credentials if the browser sends cookies; wildcards defeat the Origin restriction layer. Use an exact origins allowlist.

### Exercise 7 — Why not put Bearer tokens in the WebSocket URL query string?

**Answer:** Query strings can appear in proxy/access logs, traces, and analytics, leading to token leakage. Design safer session/ticket/auth metadata, reduce TTL, and redact.

### Exercise 8 — Are CORS and Origin the same thing?

**Answer:** CORS is the browser HTTP cross-origin access protocol; the `Origin` header is metadata about the page source. For WebSockets, the server must evaluate `Origin`; reactive CORS configuration can be used, but must be tested directly.

### Exercise 9 — Local frontend 3000 and WS backend 8080?

**Answer:** The browser Origin is typically `http://localhost:3000`, not `ws://localhost:8080`. Allow the dev origin explicitly if policy permits; production must not allow insecure local origins.

### Exercise 10 — Token expires during a WebSocket session?

**Answer:** HTTP security does not automatically re-run on every frame. Enforce max connection age, reauth, close on revocation/expiry, and authorize sensitive actions.

### Exercise 11 — Does RSocket-over-WebSocket use raw WebSocketHandler?

**Answer:** Not as a raw text handler. RSocket has its own SETUP/frames/routes. Boot has mapping-path `/rsocket`; Origin policy at the HTTP transport and `RSocketSecurity` at payload/route are two layers.

### Exercise 12 — Does RSocket TCP have an Origin header?

**Answer:** No, because there is no HTTP WebSocket handshake. Use TLS, RSocket SETUP authentication, route authorization, and network policies.

### Exercise 13 — Is a WebTestClient GET without Upgrade enough to prove the handshake?

**Answer:** No. It verifies HTTP filters, not 101. You need a `WebSocketClient`/real HTTP Upgrade test.

### Exercise 14 — When is a missing Origin header allowed?

**Answer:** Only when there is a **separate policy** for trusted non-browser clients with appropriate authentication/network/mTLS controls. The demo browser endpoint intentionally rejects missing Origins.

### Exercise 15 — When the same hostname serves multiple tenants?

**Answer:** An Origin allowlist does not verify tenant membership. You need binding of verified tenant/subject/room and record-level ACLs; never trust a tenant string sent by a message/client.

### Exercise 16 — Why is TLS needed behind a reverse proxy?

**Answer:** The proxy may terminate public TLS, yet the internal hop still carries cookies/credentials/PII. Per threat model, enforce mTLS/HTTPS/service mesh and ingress restrictions.

### Exercise 17 — Can a browser set `Authorization: Bearer` in `new WebSocket`?

**Answer:** The native `WebSocket` constructor does not allow setting arbitrary HTTP `Authorization` headers. Use session cookies or a protected short-lived ticket design; non-browser clients can set headers separately.

### Exercise 18 — Why check exact scheme + host + port for Origin?

**Answer:** `http` vs `https` or a different port is a different origin; wildcard/suffix checks widen permissions for unintended pages. A strict full-origin allowlist reduces errors.

## 13. Production checklist

- [ ] Protect every WebSocket path at ingress and in `SecurityWebFilterChain`.
- [ ] Server-side strict Origin allowlist; never rely on browser CORS to block it.
- [ ] Never allow wildcard Origin on cookie-authenticated endpoints.
- [ ] Reject missing/duplicate/`null` Origins per browser policy.
- [ ] Origin uses the page's `http(s)` scheme, never confused with `ws(s)` target.
- [ ] Authenticate independently via session/Bearer/mTLS; Origin is not identity.
- [ ] Browser session cookies have proper `Secure`/`HttpOnly`/`SameSite`/expiry/rotation.
- [ ] CSRF protects login/unsafe HTTP flows; never assume GET Upgrade carries a token.
- [ ] One-time tickets for sensitive sockets if required by threat model, never leaked to URLs/logs.
- [ ] Handshake policy and message-level ACL are independent.
- [ ] Recheck tenant/owner/permissions on every sensitive action.
- [ ] Close or re-auth connections when tokens/sessions expire, log out, or are revoked.
- [ ] Enforce message schemas, allowed frame types, max frame sizes, and rate quotas.
- [ ] Set connection/idle/max-lifetime limits, cancellation/backpressure/heartbeats.
- [ ] Enforce WSS/TLS at public endpoints and proper internal hop security.
- [ ] Trusted proxies/forwarded headers; avoid deriving Origin policy from spoofed `Host`.
- [ ] Never expose raw Authorization/Cookie/CSRF tickets in logs/traces.
- [ ] Test HTTP filters with `WebTestClient`: proper 401/403.
- [ ] Test WebSocket Upgrade with `ReactorNettyWebSocketClient`: success/fail.
- [ ] Test browser cookie CSWSH and allowed/evil Origins in staging.
- [ ] For RSocket-over-WebSocket, separately protect `/rsocket` and RSocket routes/SETUP.
- [ ] Never confuse Servlet STOMP security APIs with raw WebFlux WS/RSocket.
- [ ] Monitor active connections, errors, quota breaches, and revocation lifecycles.

## 14. Core summary

```text
HTTP handshake:
  Origin allowlist -> Authentication -> Authorization -> Upgrade
   wrong Origin       missing token     missing role     success
       403                401               403            101

After Upgrade:
  SecurityWebFilterChain DOES NOT auto-rerun per frame
  -> WebSocketHandler needs per-message schema + ACL + tenant policy
  -> deadline/logout/revocation need session/connection lifecycle control

Browser:
  new WebSocket(url), CANNOT set arbitrary custom Authorization header
  -> typically uses cookies/sessions or one-time tickets
  -> CSWSH prevention: strict Origin + credential validation

RSocket:
  WebSocket transport handshake Origin is one layer
  RSocket SETUP authentication + route authorization is another layer
```

**Conclusion:** Checking Origin during the **server-side handshake** is a critical line of defense against Cross-Site WebSocket Hijacking, especially with cookie sessions. Yet Origin is not authentication, an HTTP handshake does not automatically protect individual frames, and a long-lived connection does not automatically lose permissions when a token expires. A secure architecture must protect **before upgrade, on every message, and throughout the socket's lifecycle**.

## 15. References

- [Spring Framework 6.2 — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-websocket.html)
- [Spring Framework 6.2 — WebFlux Configuration/WebSocketService](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Framework 6.2 — WebFlux CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [Spring Framework 6.2 — HandshakeWebSocketService API](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/reactive/socket/server/support/HandshakeWebSocketService.html)
- [Spring Security 6.5 — Reactive HTTP WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — WebSocket Security (Servlet/STOMP; does not apply directly to raw WebFlux)](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html)
- [Spring Security — Reactive RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [Spring Boot 3.5 — RSocket over WebSocket](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
- [RFC 6454 — The Web Origin Concept](https://www.rfc-editor.org/rfc/rfc6454)
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
