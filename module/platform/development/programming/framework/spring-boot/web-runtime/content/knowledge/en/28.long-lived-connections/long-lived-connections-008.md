# Origin, Handshake, and WebSocket Connection Authentication in Spring Boot

## 1. Objectives and Problem Statement

WebSocket establishes a **bidirectional (full-duplex)** communication channel that can remain open for a long time between client and server. Unlike a REST API that processes individual HTTP request/response cycles, once the connection is upgraded, both sides can send multiple **WebSocket frames/messages** without initiating a new HTTP request per message.

This raises three independent security questions:

1. **Origin:** Which web page is trying to open a WebSocket from the browser? Should that page be allowed to establish a connection?
2. **Handshake:** Is the opening request valid per the WebSocket protocol, and has it passed properly through proxies and security filters?
3. **Authentication and authorization:** What identity is the client using? Is that identity permitted to **open the connection** and **send/receive each message type**?

A secure configuration must enforce **all three**, rather than merely allowing HTTP `GET` on `/ws` and hoping security automatically protects every subsequent message.

This lesson belongs to the **Long-lived connections** topic in Spring Boot web runtime, focusing on **WebSocket on Spring MVC/Servlet**, Java 17+, Spring Framework 6.2, and Spring Security 6.5. The runnable example uses **raw WebSocket `TextWebSocketHandler`** paired with **form login/session cookies**, then compares **STOMP over WebSocket**, SockJS, WebFlux, API tokens, and reverse proxy infrastructure.

After this lesson, you will be able to:

- Read an HTTP `Upgrade` handshake and `101 Switching Protocols` response.
- Explain why `Origin` **is not a credential**, yet remains a key defense against **Cross-Site WebSocket Hijacking (CSWSH)** in browsers.
- Configure `WebSocketHandlerRegistry.setAllowedOrigins(...)` and Spring Security filter rules consistently.
- Understand how the `Principal` from the HTTP request transfers to `WebSocketSession` once the connection is accepted.
- Distinguish **HTTP form CSRF** from **STOMP `CONNECT` CSRF**: avoid mechanically applying STOMP rules to raw WebSocket.
- Verify that missing login or disallowed Origin rejects the handshake, while post-`101` messages must be handled with WebSocket semantics.
- Design message-level authorization, timeouts, limits, and lifecycles for long-lived connections.

**Core message:** `Origin` answers "which web page initiated the request as reported by the browser"; authentication answers "who is the verified client"; authorization answers "what is the client permitted to do". Never substitute one question for another.

## 2. WebSocket Handshake: Starts as HTTP, Does Not Continue as Normal HTTP

### 2.1. Example HTTP/1.1 Handshake

Browser JavaScript:

```javascript
const socket = new WebSocket("wss://app.example.com/ws/chat");
```

In the **WebSocket HTTP/1.1 Upgrade** model, the opening request typically looks like:

```http
GET /ws/chat HTTP/1.1
Host: app.example.com
Origin: https://app.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Cookie: JSESSIONID=<cookie-value-sent-by-browser>
```

This is a structural example; cookie and key values vary in real systems. **Never copy real cookies or session IDs into docs, logs, or issue trackers.**

If the request is valid, permitted, and the server accepts the upgrade:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

The `Sec-WebSocket-Accept` value above is the standard RFC 6455 sample output for the shown `Sec-WebSocket-Key`. The server computes it from the key and the standard GUID using SHA-1 + Base64; this calculation **verifies protocol handshake compliance, not user identity or connection security**.

Key headers:

| Component | Role | Security Note |
| --- | --- | --- |
| `GET` | In HTTP/1.1 Upgrade, WebSocket begins with GET | Does not imply "no state-changing effects" once open |
| `Upgrade: websocket` | Requests protocol switch | Meaningful only for valid handshake versions/proxies |
| `Connection: Upgrade` | Marks hop-by-hop header in HTTP/1.1 | Reverse proxies must forward it properly |
| `Sec-WebSocket-Key` | Random nonce for handshake | **Not an API key or auth token** |
| `Sec-WebSocket-Accept` | Proof the server understood the handshake key | **Does not** prove the user is authenticated |
| `Sec-WebSocket-Version: 13` | Specifies standard WebSocket version per RFC 6455 | Unsupported versions may be rejected |
| `Origin: https://...` | Web page origin reported by browser | Used for cross-site checks; non-browsers can spoof it |
| `Cookie: JSESSIONID=...` | Browser sends matching cookies per domain/path/SameSite/Secure | Session cookies are credentials; must defend against CSWSH |
| `Sec-WebSocket-Protocol` | Proposes one or more subprotocols like `v12.stomp` | Must be negotiated properly; never abuse as an arbitrary credential |

**Note:** Not every WebSocket on the internet uses HTTP/1.1 `Upgrade` headers. HTTP/2 defines **Extended CONNECT** for WebSocket (RFC 8441), whose support depends on client, edge proxy, and server. This hands-on lesson uses common HTTP/1.1 Upgrade; do not require `Connection: Upgrade` on HTTP/2 because hop-by-hop headers are not used there as in HTTP/1.1.

### 2.2. Why Is `Origin` `https://...` Rather Than `wss://...`?

`Origin` describes **the origin of the page creating the connection**, comprising **scheme, host, and port**, such as `https://app.example.com`. The WebSocket URL uses `ws://` or `wss://`, which is the **connection target**, not the page's origin.

Example:

```text
Web page:          https://app.example.com/dashboard
Target WebSocket:  wss://app.example.com/ws/chat
Origin sent:       https://app.example.com

Malicious page:    https://attacker.example/
Target WebSocket:  wss://app.example.com/ws/chat
Origin sent:       https://attacker.example
```

**Paths are not part of an origin.** `https://app.example.com/a` and `https://app.example.com/b` share the same origin; `http://app.example.com` and `https://app.example.com` have different origins despite sharing the host.

### 2.3. Rejecting the Handshake Differs from Rejecting a Message

Before completing `101`, the server is still handling an HTTP request. It can return:

- **302** redirect to `/login` when using Spring Security form login and the client is unauthenticated.
- **401** + challenge when the entry point uses HTTP Basic or Bearer API authentication.
- **403** when Origin is disallowed or another policy rejects the request.
- **400** when WebSocket handshake headers are missing or malformed.
- **404** when no handler matches the URL or routing is misconfigured.
- **426 Upgrade Required** in certain systems/gateways depending on contract.

After `101`, the connection has switched to WebSocket. At that point **you cannot turn a failing WebSocket message into an HTTP 403 response** on that connection like a fresh request. The server must send an **application error message**, close the WebSocket with an appropriate close code, or reject the command per STOMP protocol rules if using STOMP.

Common close codes:

| Close Code | General Meaning | Example |
| --- | --- | --- |
| `1000` | Normal closure | Browser leaves page, session completes |
| `1001` | Endpoint "going away" | Server shutdown or page closed |
| `1008` | Policy violation | Unauthorized message / invalid identity |
| `1009` | Message too big | Payload exceeds limit |
| `1011` | Internal server error | Unexpected error while processing message |
| `1006` | Abnormal closure (reserved, observation only) | Connection dropped without receiving a close frame |

`1006` is reserved for **local status reporting**—**never send it inside a WebSocket Close frame**. Specific close reasons and statuses must follow RFC 6455 and app policies without leaking secrets or stack traces.

## 3. Origin: Why Do Browsers Need a Dedicated Barrier?

### 3.1. WebSocket Is Not Bound by CORS the Way `fetch` Is

Browsers enforce the **same-origin policy** and CORS on many JavaScript HTTP requests, yet **the WebSocket API does not rely on standard CORS preflight `OPTIONS` checks**. A page at `https://attacker.example` can still **attempt to open**:

```javascript
// Threat-model illustration; never run against unauthorized systems.
const ws = new WebSocket("wss://app.example.com/ws/chat");
```

If the browser automatically attaches matching login cookies and the server **fails to check `Origin`**, the malicious page can send and receive data over a connection authenticated with the victim's cookie. This is a form of **Cross-Site WebSocket Hijacking (CSWSH)**.

Contrast:

- With `fetch("https://api.example.com")`, the browser uses CORS to control whether JavaScript can read the response and issues preflights when required.
- With `new WebSocket("wss://app.example.com/ws")`, the server must **actively enforce allowed origins** during the WebSocket handshake.
- Adding `@CrossOrigin` to a REST controller **does not** configure `WebSocketHandlerRegistry` or STOMP endpoints.
- WebSocket does not perform a `fetch`-style `OPTIONS` preflight solely to ask Origin permission. Never design CSWSH defenses around allowing/denying HTTP `OPTIONS`.

### 3.2. How Spring Framework Checks Origin

Spring Framework configures WebSocket via `WebSocketConfigurer`:

```java
registry.addHandler(myHandler, "/ws/echo")
        .setAllowedOrigins("https://app.example.com");
```

This is a snippet inside `registerWebSocketHandlers`, not a full Java class. Per Spring documentation, WebSocket/SockJS handlers **accept only same-origin by default** unless expanded; `setAllowedOrigins(...)` specifies explicitly permitted origins.

**Do not use**:

```java
// ANTI-PATTERN for apps using cookies/sessions:
registry.addHandler(myHandler, "/ws/echo")
        .setAllowedOrigins("*");
```

`*` opens the endpoint to arbitrary origins; when cookies are attached automatically, CSWSH risk rises sharply. Permit only approved public origins. If multiple specific domains exist, list them explicitly or use `setAllowedOriginPatterns(...)` with tight patterns rather than broad wildcards.

**Origin is not authentication:** clients such as `curl`, Java, Python, or scripts can **set or spoof** the `Origin` header. Origin checks protect browser/cross-site flows; credential authentication and action-level authorization remain mandatory. In some libraries, a missing `Origin` header is treated differently from an invalid one; if business rules require blocking missing Origin too, handle non-browser clients explicitly with a dedicated interceptor rather than assuming `setAllowedOrigins` blocks absent headers everywhere.

### 3.3. Cookies and SameSite Do Not Replace Origin

Whether a browser sends `JSESSIONID` on the handshake depends on:

- Cookie `Domain` and `Path`.
- `Secure`, ensuring cookies travel only over secure transport.
- `HttpOnly`, blocking direct JavaScript reads without **stopping the browser from attaching the cookie to requests**.
- `SameSite` and how the browser classifies same-site vs. cross-site.
- Browser policies blocking third-party cookies.

`SameSite=Lax` or `Strict` mitigates several attack paths, yet **never justifies dropping Origin checks**: same-site does not equal same-origin (subdomains share a site yet differ in origin), browser cookie behaviors vary, and non-browser clients can spoof headers. Treat **Origin checks + authentication + message authorization + cookie protections** as defense in depth.

## 4. Handshake Authentication: Who Is the User on WebSocketSession?

Spring Security in the Servlet stack normally authenticates the **HTTP handshake request** using the active HTTP mechanism: form login/session cookie, HTTP Basic, OAuth2 login, or another method.

In a form-login setup:

```text
1. Browser GET /login
2. Browser POST /login (username + password + CSRF token)
3. Spring Security authenticates; saves SecurityContext per session policy
4. Browser holds valid session cookie
5. JavaScript calls new WebSocket("wss://app.example.com/ws/echo")
6. Browser sends HTTP GET Upgrade with cookies per policy
7. SecurityFilterChain resolves Principal on the handshake request
8. WebSocket handler validates allowed Origin / upgrades with 101
9. WebSocketSession.getPrincipal() holds the handshake identity
10. Handler reads messages and checks permissions for each action
```

Spring Security documentation confirms that **the HTTP request's Principal at handshake time is handed over to WebSocket**. With Spring MVC raw WebSocket and Spring Security session login, you usually do not need to parse `JSESSIONID` and look up the user manually.

However, important boundaries apply:

- **Handshake authentication is not authorization for every message.** `/ws/chat` might allow any logged-in user, whereas `DELETE_ORDER` or `SUBSCRIBE_ADMIN_EVENTS` still requires specific permission checks.
- **Re-authentication does not run on every frame.** The HTTP filter chain does not re-execute like GET/POST for each post-upgrade WebSocket message.
- **`SecurityContextHolder` is thread-bound** per SecurityContext rules; do not assume every background WebSocket callback inherits the HTTP handshake's ThreadLocal context. Use `WebSocketSession.getPrincipal()` and an authorization service built for connections/messages.
- A user who logs out, gets locked, or has privileges revoked **after opening the connection** may retain a live WebSocket unless the app actively closes or revalidates it. Design expiry, revocation, tenant checks, and session termination per requirements.
- Handshake session cookies are credentials; never print full cookies, `Authorization`, access tokens, or session IDs into console or client logs.

### 4.1. HTTP 302, 401, or 403 When Unauthenticated?

**Depends on the `AuthenticationEntryPoint`**:

- Browser app with `formLogin`: unauthenticated requests to `/ws/echo` may receive **302 to `/login`**.
- HTTP Basic API chain: missing credentials usually return **401** with `WWW-Authenticate`.
- Resource Server Bearer: missing/invalid bearer tokens normally return **401**; missing scope returns **403** with challenge headers.
- Origin rejected by WebSocket handler: **403** once the request passes security filters and reaches the origin check.

Never call `new WebSocket(...)` in a browser expecting it to follow a login redirect HTML page like a normal link. The WebSocket handshake expects `101`; redirecting to an HTML login page fails the connection per client/protocol rules. In browsers, users must log in over HTTP first before opening the WebSocket.

### 4.2. Browser WebSocket API Cannot Set Arbitrary Custom Authorization Headers

Standard JavaScript:

```javascript
const ws = new WebSocket("wss://api.example.com/ws/chat");
```

has no option equivalent to `fetch(..., {headers: {Authorization: ...}})` to attach **arbitrary headers** to the opening handshake. Therefore:

- **Session cookies + HTTP form/OAuth2 login** are a natural fit for same-site browser apps.
- **Native/mobile clients** can send `Authorization` headers depending on their library if the backend accepts them.
- **STOMP over WebSocket** can carry auth metadata inside the STOMP `CONNECT` frame post-handshake, provided a `ChannelInterceptor`/message-level auth layer verifies it properly; never trust CONNECT headers as a Principal without verification.
- **Avoid stuffing long-lived JWTs into query strings like `?token=...`**: URLs leak into logs, tracing, monitoring, proxies, bookmarks, and error reports. If a URL token is unavoidable, use a tightly scoped, short-lived, single-use token bound to audience over HTTPS/WSS with log redaction—an explicit design, not a casual workaround.
- `Sec-WebSocket-Protocol` negotiates subprotocols and should not be abused as an arbitrary bearer-token tunnel without clear policy and subprotocol design.

Never treat `Origin` as a credential in place of tokens or sessions: any non-browser client can send `Origin: https://trusted.example`.

## 5. HandshakeInterceptor, HandshakeHandler, and Spring Security Filter Chain

Key extension points:

| Mechanism | When It Runs | Purpose | Does Not Replace |
| --- | --- | --- | --- |
| `SecurityFilterChain` (Servlet) | HTTP handshake request, before controller/handler | Authentication, URL authorization, HTTP CSRF policy | Per-message authorization |
| `OriginHandshakeInterceptor` / `setAllowedOrigins` | During WebSocket handshake | Validate allowed origins | Credential verification |
| Custom `HandshakeInterceptor` | Before/after handshake | Reject handshake per policy or copy **safe attributes** to WebSocket session | Authentication providers / full security policy |
| `HandshakeHandler` / `DefaultHandshakeHandler` | HTTP upgrade and Principal/subprotocol selection | Customize negotiation or Principal resolution when truly needed | Permission checks for business messages |
| `TextWebSocketHandler` / `WebSocketHandler` | After `101` upgrade, handling messages/close/errors | Message validation, business permissions, responses | HTTP filters per message |
| STOMP `ChannelInterceptor` / Spring Messaging authz | STOMP `CONNECT`/`SEND`/`SUBSCRIBE`... | Token verification, destination-level authorization | Origin checks at HTTP handshake |

For instance, a `HandshakeInterceptor` can load verified metadata from a database, enforce per-user socket quotas, or copy attributes from the HTTP session into the WebSocket session. Never copy entire sessions, cookies, or tokens unnecessarily; a `WebSocketSession` can outlive a single HTTP request.

**Watch out with `HttpSessionHandshakeInterceptor`:** when configured, it copies selected HTTP session attributes into the WebSocket session attribute map. **It is not an authentication filter** and grants no access merely because a session holds a `"user"` string. When Spring Security already authenticated the request, rely on the verified `Principal` rather than an input-influenced `loggedIn=true` flag.

When using cookie/session auth with Spring Security, the cleanest raw WebSocket setup is: **guard the handshake URL with `authenticated()`, restrict allowed origins, and check `Principal` when handling messages**. Write extra handshake interceptors only when facing a requirement the framework does not already handle.

## 6. Runnable Spring Boot Java 17+ Application Example

The demo provides:

- `GET /login`: Spring MVC + Thymeleaf login form with CSRF token.
- `POST /login`: Spring Security authenticates the session.
- `GET /app`: HTML page requiring login that connects WebSocket from the same origin.
- `GET /ws/echo`: WebSocket handshake endpoint requiring Spring Security authentication.
- `TextWebSocketHandler`: post-`101`, echoes messages prefixed with the Principal's name, enforces a size limit, and rejects missing Principals.

The demo uses **Spring Boot 3.5.16** with Spring Security from the Boot 3.5 BOM, **Java 17+**, and default embedded Tomcat. Boot 3.5.16 is released as **the final OSS-supported release in the 3.5.x line**; new production projects should target a currently maintained line (4.0/4.1 or newer) and adjust APIs/imports accordingly. Pinning the version here gives learners a reproducible baseline.

**Use demo accounts only on localhost; never publish an app with sample passwords, and never use fake TLS certs pretending it is production WSS.**

### 6.1. Project Structure

```text
websocket-origin-demo/
├─ pom.xml
└─ src/
   ├─ main/
   │  ├─ java/com/example/demo/
   │  │  ├─ WebSocketOriginApplication.java
   │  │  ├─ WebSecurityConfiguration.java
   │  │  ├─ EchoWebSocketHandler.java
   │  │  ├─ WebSocketConfiguration.java
   │  │  └─ PageController.java
   │  └─ resources/
   │     ├─ application.properties
   │     └─ templates/
   │        ├─ login.html
   │        └─ app.html
   └─ test/
      └─ java/com/example/demo/
         └─ WebSocketOriginApplicationTest.java
```

### 6.2. Maven Dependencies

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>websocket-origin-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
```

`spring-boot-starter-websocket` brings Servlet WebSocket support and required web dependencies in Boot 3.5. `spring-boot-starter-thymeleaf` renders forms/pages; `spring-security-test` supplies `MockMvc` helpers such as `csrf()` and `user()`.

### 6.3. Application Properties

**`src/main/resources/application.properties`**

```properties
server.port=8080

# Only browser apps running at this URL may open WebSocket.
# Origin must be the http(s) origin of the PAGE, never ws://.
app.websocket.allowed-origin=http://localhost:8080

# Cookie settings for local HTTP learning.
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

Production HTTPS needs proper `Secure` cookies (e.g., `server.servlet.session.cookie.secure=true`), trusted proxy headers/TLS, and an exact public allowed origin like `https://app.example.com`. Never enable `Secure` cookies for a plain HTTP learning app and wonder why session login breaks.

### 6.4. Main Class

**`src/main/java/com/example/demo/WebSocketOriginApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketOriginApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSocketOriginApplication.class, args);
    }
}
```

### 6.5. Spring Security: Authenticating the HTTP Handshake

**`src/main/java/com/example/demo/WebSecurityConfiguration.java`**

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/error").permitAll()
            .requestMatchers("/app", "/ws/echo").authenticated()
            .anyRequest().denyAll()
        ).formLogin(form -> form
            .loginPage("/login")
            .defaultSuccessUrl("/app", true)
            .permitAll()
        );

        // Keep Spring Security's default CSRF for HTML POSTs.
        // Raw WebSocket handshake is GET; validate messages after 101.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails demo = User.withUsername("demo")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(demo);
    }
}
```

**Why this configuration fits form login:**

1. `/login` is accessible before login; `/app` and `/ws/echo` require authentication.
2. Logging in via HTML `POST /login` retains **CSRF protection**. Because the WebSocket handshake request is an HTTP GET, default `CsrfFilter` does not demand a CSRF token on it.
3. `defaultSuccessUrl("/app", true)` sends logged-in users directly to the demo page; real apps using saved requests must prevent open redirects.
4. `anyRequest().denyAll()` avoids accidentally exposing new routes publicly.
5. The sample password is BCrypt-encoded before entering `InMemoryUserDetailsManager`; still, never hardcode real passwords in source control.
6. Spring Security manages the HTTP request's principal. **Never derive a user from `Origin`**, and never trust a `userId` field sent by the WebSocket client.
7. `/ws/echo` requires only `authenticated()` rather than a specific role since the demo only echoes text. For real business operations, check permissions **per message/object** in the handler or STOMP messaging layer.

### 6.6. Raw WebSocket Handler: Never Trust Client Data

**`src/main/java/com/example/demo/EchoWebSocketHandler.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.security.Principal;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class EchoWebSocketHandler extends TextWebSocketHandler {

    // Demo application limit in UTF-16 chars, not bytes.
    private static final int MAX_TEXT_LENGTH = 1024;

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws IOException {

        Principal principal = session.getPrincipal();
        if (principal == null) {
            session.close(CloseStatus.POLICY_VIOLATION);
            return;
        }

        String text = message.getPayload();

        if (text.length() > MAX_TEXT_LENGTH) {
            session.close(CloseStatus.TOO_BIG_TO_PROCESS);
            return;
        }

        session.sendMessage(
            new TextMessage(principal.getName() + ": " + text)
        );
    }
}
```

Here:

- `session.getPrincipal()` comes from the authenticated HTTP handshake; the handler **does not take the username from the body**.
- The `1024`-character limit is an **application-level demo guard**. Real systems must also enforce **byte/frame/buffer** limits on the WebSocket container so huge messages are not buffered before checking.
- `CloseStatus.POLICY_VIOLATION` maps to **1008**; `TOO_BIG_TO_PROCESS` maps to **1009**.
- The handler performs no business mutations. For messages modifying accounts, sending documents, subscribing to rooms, or payments, parse against a schema, validate payloads, authenticate/authorize the action, and enforce resource ownership per message.
- Never inject payloads into browser HTML as markup. The demo client uses `textContent` instead of `innerHTML`.

**Concurrency:** `WebSocketSession.sendMessage` does not guarantee arbitrary threads may call it simultaneously on the same session. When multiple threads push messages to one session, consider `ConcurrentWebSocketSessionDecorator` with send time/buffer limits and clear event ordering. This example sends only one reply per incoming message without building a broadcast system.

### 6.7. Configuring the WebSocket Endpoint and Origin Allowlist

**`src/main/java/com/example/demo/WebSocketConfiguration.java`**

```java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoWebSocketHandler handler;
    private final String allowedOrigin;

    public WebSocketConfiguration(
            EchoWebSocketHandler handler,
            @Value("${app.websocket.allowed-origin}") String allowedOrigin) {
        this.handler = handler;
        this.allowedOrigin = allowedOrigin;
    }

    @Override
    public void registerWebSocketHandlers(
            WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/echo")
                .setAllowedOrigins(allowedOrigin);
    }
}
```

When visiting `http://localhost:8080/app`, the browser sends `Origin: http://localhost:8080` for `ws://localhost:8080/ws/echo`, matching the allowlist. A page at `https://attacker.example` attempting to open the same socket sends a different Origin and gets rejected when it hits the origin checker.

**Never set `ws://localhost:8080` in `app.websocket.allowed-origin`.** Spring compares the HTTP(S) origin of the page, not the WebSocket URL scheme.

Having two layers of defense is deliberate:

1. **Spring Security URL rule** blocks unauthenticated handshakes.
2. **Spring WebSocket Origin restriction** blocks disallowed browser origins.

To keep the demo focused, SockJS is omitted and neither `@EnableWebSocketMessageBroker` nor STOMP messaging is configured; raw WebSocket differs from a broker with destinations, SUBSCRIBE, and CONNECT frames.

### 6.8. Controller Rendering the Login and App Pages

**`src/main/java/com/example/demo/PageController.java`**

```java
package com.example.demo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/app")
    public String app() {
        return "app";
    }
}
```

`@Controller` returns template names `login` and `app`. Changing it to `@RestController` would make Spring return literal strings instead of rendering HTML—a common Spring MVC mistake.

### 6.9. Login Page with CSRF Token

**`src/main/resources/templates/login.html`**

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Login WebSocket Demo</title>
</head>
<body>
  <h1>Sign In</h1>

  <p th:if="${param.error}">
    Invalid username or password.
  </p>

  <form method="post" th:action="@{/login}">
    <label for="username">Username</label>
    <input id="username" name="username" required>

    <label for="password">Password</label>
    <input id="password" name="password" type="password" required>

    <button type="submit">Sign in</button>
  </form>
</body>
</html>
```

With standard Spring Security/Thymeleaf integration, a POST form using `th:action` automatically injects a hidden CSRF token input. Tokens **must not be hardcoded** and vary per session/protection policy. Without the token, `POST /login` returns 403 due to CSRF; that is distinct from an Origin rejection during the WebSocket handshake.

### 6.10. App Page Opening WebSocket After Login

**`src/main/resources/templates/app.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>WebSocket Echo</title>
</head>
<body>
  <h1>WebSocket echo after login</h1>
  <p id="connection-status">Connecting...</p>

  <label for="message">Message</label>
  <input id="message" maxlength="1024" value="Hello">
  <button id="send" disabled>Send</button>

  <h2>Server log</h2>
  <div id="messages" aria-live="polite"></div>

  <script>
    const status = document.getElementById("connection-status");
    const input = document.getElementById("message");
    const send = document.getElementById("send");
    const log = document.getElementById("messages");

    // Fixed path for root-context localhost demo.
    // Behind a path-prefix proxy, use a context-aware URL builder.
    const scheme = location.protocol === "https:" ? "wss://" : "ws://";
    const url = scheme + location.host + "/ws/echo";

    const socket = new WebSocket(url);

    socket.addEventListener("open", () => {
      status.textContent = "Connected";
      send.disabled = false;
    });

    socket.addEventListener("message", event => {
      const row = document.createElement("p");
      row.textContent = event.data; // Text only; never use innerHTML.
      log.appendChild(row);
    });

    socket.addEventListener("close", event => {
      status.textContent = "Closed: code " + event.code;
      send.disabled = true;
    });

    socket.addEventListener("error", () => {
      // Browsers withhold detailed HTTP handshake responses from JavaScript.
      status.textContent = "Connection failed";
      send.disabled = true;
    });

    send.addEventListener("click", () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(input.value);
      }
    });

    window.addEventListener("beforeunload", () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.close(1000, "Leaving page");
      }
    });
  </script>
</body>
</html>
```

**Client-side security notes:**

- `new WebSocket(url)` offers no way to pass an arbitrary `Authorization` header. Session cookies are sent automatically by the browser when eligible.
- The URL selects `wss://` on HTTPS pages; **never** open `ws://` from a production HTTPS page (mixed-content/security failure).
- `row.textContent = event.data` renders payloads safely as text without interpreting HTML/JS; `innerHTML` invites XSS on untrusted data.
- Browser UI `maxlength=1024` is only a UX convenience; the server **still enforces** `MAX_TEXT_LENGTH`.
- `onerror` normally **hides HTTP 302/403/400 details** due to browser WebSocket security restrictions. Inspect Network → WS/Headers and server logs to find the root cause.
- Inline JS is used in the demo for readability; production apps with strict CSP should place JS in separate static files instead of enabling `unsafe-inline`.

## 7. Step-by-Step Run and Verification

### 7.1. Starting the App

In the project folder with JDK 17+ and Maven:

```bash
java -version
mvn spring-boot:run
```

If created via Spring Initializr with the Maven Wrapper:

```bash
./mvnw spring-boot:run
```

On Windows use `mvnw.cmd spring-boot:run`. By default the demo listens on `http://localhost:8080`; make sure that port is free.

### 7.2. Unauthenticated Browser

Open:

```text
http://localhost:8080/app
```

Expect a **redirect to `/login`**. That is the Spring Security form-login rule for `/app`, prior to any WebSocket handshake.

If a script tries connecting directly to `ws://localhost:8080/ws/echo` without a login session, the security filter intercepts the HTTP handshake. With `formLogin`, the server returns `302 /login`; the WebSocket client treats any non-`101` response as a handshake failure. **Never expect a browser WebSocket to render a login form through a redirect.**

### 7.3. Logging In and Opening WebSocket

On the login page, enter:

```text
username: demo
password: demo-pass
```

The browser submits a POST form with a CSRF token; Spring Security authenticates and creates the session. Once `/app` loads, JavaScript connects to:

```text
ws://localhost:8080/ws/echo
```

In DevTools → Network → WS (or equivalent), expect the handshake request returning **101 Switching Protocols**. When clicking **Send** with `Hello`, the handler returns:

```text
demo: Hello
```

That is **the expected payload inside a Message event**, not a plain HTTP GET response body. Inspect the Frames/Messages tab to watch traffic flow in both directions. Repeated clicks reuse the same open WebSocket session across multiple messages.

**Do not use `curl -i http://localhost:8080/ws/echo` as proof "WebSocket works"**: a plain HTTP GET lacks Upgrade/Key/Version headers and does not speak WebSocket frames, so it triggers a redirect or 400. Verify handshakes with a browser, a WebSocket-aware client, or a real WebSocket integration test.

### 7.4. Disallowed Origin

To observe the policy, **log in first** and issue a handshake with a valid session cookie yet a different `Origin`. Once past the security filter, Origin validation rejects the handshake, normally with **403**.

Do not send a request that is both **unauthenticated** and **bad-Origin** and conclude Origin policy was tested: Spring Security may redirect to login **before** the Origin interceptor runs. Distinguish which layer rejected the request.

The HTTP snippet below illustrates the headers only (cannot substitute for a full WebSocket client):

```http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Origin: https://attacker.example
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Cookie: JSESSIONID=<valid-logged-in-cookie>
```

Expected Origin policy outcome with valid authentication: **no 101**, typically **403**. Never place real session cookies on public command lines or shared history just to test; use a `MockMvc` or unit test with an authenticated principal as shown next.

### 7.5. Missing or Invalid Handshake Headers

Even when authenticated with a valid Origin, a request lacking:

- `Upgrade: websocket`,
- `Connection: Upgrade` (for HTTP/1.1),
- a supported `Sec-WebSocket-Version`,
- a valid `Sec-WebSocket-Key`,

will not be accepted as an HTTP/1.1 WebSocket connection. Depending on the layer and exact error, the server normally returns 400 or another handshake error—**not** everything returns 403.

### 7.6. Long-Lived Connections and Sessions

A WebSocket can stay open for minutes or hours while the HTTP session cookie expires or the user logs out in another tab. **Never assume Spring Security re-authenticates every message.** Sensitive systems need:

- Maximum WebSocket session lifetimes.
- Closing sessions on logout/revocation or revalidating permissions before sensitive actions.
- Comparing `Principal` against current account state if business policy requires immediate enforcement.
- Spring Session WebSocket integration when coordinating HTTP session timeouts with WebSockets; never assume an open WebSocket keeps an HTTP session alive forever by itself.
- Verifying whether the session still holds room/topic subscription rights, removing subscriptions or closing on revocation.

## 8. Testing Spring MVC, Origin, and the Message Handler

The tests below use `spring-boot-starter-test` and `spring-security-test`. They verify **Spring Security HTTP rules**, **OriginHandshakeInterceptor policy**, and **handler behavior** without needing external sockets.

**`src/test/java/com/example/demo/WebSocketOriginApplicationTest.java`**

```java
package com.example.demo;

import java.util.HashMap;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServletServerHttpRequest;
import org.springframework.http.server.ServletServerHttpResponse;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.server.support.OriginHandshakeInterceptor;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class WebSocketOriginApplicationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    EchoWebSocketHandler handler;

    @Test
    void anonymousBrowserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/app"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")
            ));
    }

    @Test
    void anonymousHandshakeIsNotAllowed() throws Exception {
        mvc.perform(get("/ws/echo"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")
            ));
    }

    @Test
    void authenticatedUserCanLoadPage() throws Exception {
        mvc.perform(get("/app")
                .with(user("demo").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("new WebSocket(url)")
            ));
    }

    @Test
    void missingCsrfTokenRejectsLoginPost() throws Exception {
        mvc.perform(post("/login")
                .param("username", "demo")
                .param("password", "demo-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validFormLoginWithCsrfRedirectsToApp()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "demo")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/app"));
    }

    @Test
    void originPolicyRejectsCrossSiteHandshake() throws Exception {
        var request = new MockHttpServletRequest("GET", "/ws/echo");
        request.setScheme("http");
        request.setServerName("localhost");
        request.setServerPort(8080);
        request.addHeader("Origin", "https://attacker.example");

        var response = new MockHttpServletResponse();
        var interceptor = new OriginHandshakeInterceptor(
            List.of("http://localhost:8080")
        );

        boolean allowed = interceptor.beforeHandshake(
            new ServletServerHttpRequest(request),
            new ServletServerHttpResponse(response),
            handler,
            new HashMap<>()
        );

        assertFalse(allowed);
        assertEquals(
            HttpStatus.FORBIDDEN.value(),
            response.getStatus()
        );
    }

    @Test
    void originPolicyAllowsConfiguredOrigin() throws Exception {
        var request = new MockHttpServletRequest("GET", "/ws/echo");
        request.setScheme("http");
        request.setServerName("localhost");
        request.setServerPort(8080);
        request.addHeader("Origin", "http://localhost:8080");

        var response = new MockHttpServletResponse();
        var interceptor = new OriginHandshakeInterceptor(
            List.of("http://localhost:8080")
        );

        boolean allowed = interceptor.beforeHandshake(
            new ServletServerHttpRequest(request),
            new ServletServerHttpResponse(response),
            handler,
            new HashMap<>()
        );

        assertTrue(allowed);
    }

    @Test
    void handlerEchoesAuthenticatedPrincipalNotClientUser()
            throws Exception {
        WebSocketSession session = mock(WebSocketSession.class);
        when(session.getPrincipal()).thenReturn(() -> "demo");

        handler.handleMessage(session, new TextMessage("Hello"));

        verify(session).sendMessage(argThat(msg ->
            msg instanceof TextMessage text &&
            "demo: Hello".equals(text.getPayload())
        ));
    }

    @Test
    void handlerClosesWhenMessageIsTooLong()
            throws Exception {
        WebSocketSession session = mock(WebSocketSession.class);
        when(session.getPrincipal()).thenReturn(() -> "demo");

        handler.handleMessage(session, new TextMessage(
            "X".repeat(1025)
        ));

        verify(session).close(CloseStatus.TOO_BIG_TO_PROCESS);
        verify(session, never()).sendMessage(
            any(org.springframework.web.socket.WebSocketMessage.class)
        );
    }

    @Test
    void handlerClosesWhenPrincipalIsMissing()
            throws Exception {
        WebSocketSession session = mock(WebSocketSession.class);

        handler.handleMessage(session, new TextMessage("hello"));

        verify(session).close(CloseStatus.POLICY_VIOLATION);
    }
}
```

Run:

```bash
mvn test
```

**Expected result:** with Spring Boot 3.5.16, Spring Security/Thymeleaf/WebSocket, and the exact files above, all ten tests are designed to **pass**. This is an **expected outcome**, not a claim of having executed them in a live repository.

What these tests prove:

- Anonymous requests cannot bypass `authenticated()` rules on the page or the WebSocket handshake URL.
- Form login without CSRF is rejected; form login with a token completes the security workflow.
- The allowed-Origin policy rejects an unknown origin and permits the configured origin.
- `TextWebSocketHandler` uses the session's `Principal`, never a client-supplied username; it closes with 1008/1009 in the respective failure cases.

**Test limitations:** `OriginHandshakeInterceptor` tests are **direct unit tests of the policy**, not proof that Nginx/gateways forward `Origin` intact or that real HTTP Upgrades return 101. `MockMvc` establishes neither real WebSocket connections nor browser cookies, server resource limits, or frames/ping/pong. For full production QA, run browser/WebSocket integration tests against a real embedded server and **through the public HTTPS reverse proxy**, inspecting frames, close codes, auth/Origin, and socket errors in Network tab or a WebSocket client test library.

## 9. When Using STOMP over WebSocket: Authentication, CONNECT, and Message Authorization

The raw WebSocket example sends plain text messages. **STOMP** is a **messaging subprotocol** running over WebSocket with frames like:

```text
CONNECT
accept-version:1.2
heart-beat:10000,10000

^@
```

`^@` denotes the null byte terminating a STOMP frame, not two literal characters. Once connected, clients can send `SEND`, `SUBSCRIBE`, `UNSUBSCRIBE`, and `DISCONNECT`.

There are **two layers**:

1. The HTTP WebSocket handshake opens the transport and identifies the user over HTTP.
2. STOMP `CONNECT` opens the logical messaging session and can carry dedicated auth/CSRF metadata.

With Spring Security **WebSocket messaging security** via `@EnableWebSocketSecurity`, Spring requires a CSRF token on inbound STOMP `CONNECT` frames to reinforce same-origin checks and prevent cross-site WebSocket message submission. Do not confuse the models:

- **Raw WebSocket `TextWebSocketHandler` from section 6**: has no STOMP `CONNECT`, so STOMP `CONNECT` CSRF rules do not apply automatically.
- **Spring STOMP messaging stack**: uses `@MessageMapping`, broker prefixes, STOMP CONNECT/SUBSCRIBE, message security, and messaging-layer CSRF when configured.
- **HTTP CSRF filter**: continues protecting state-changing HTTP requests such as login/logout POSTs. A WebSocket GET handshake does not trigger HTTP `CsrfFilter` token requirements.

### 9.1. Configuring STOMP Message Authorization by Principle

A separate STOMP app configuration can use Spring Security's `@EnableWebSocketSecurity` and an `AuthorizationManager<Message<?>>` bean rather than relying only on HTTP `authenticated()`.

**Illustrative snippet — do not place into section 6's raw WebSocket demo:**

```java
// Assumes STOMP WebSocket endpoints, a message broker,
// and Spring Security messaging are configured.
@Bean
AuthorizationManager<Message<?>> messageAuthorizationManager(
        MessageMatcherDelegatingAuthorizationManager.Builder messages) {
    return messages
        .simpDestMatchers("/app/public").authenticated()
        .simpDestMatchers("/app/admin/**").hasRole("ADMIN")
        .simpSubscribeDestMatchers("/user/**").authenticated()
        .anyMessage().denyAll()
        .build();
}
```

This is a snippet requiring imports for `AuthorizationManager`, `Message`, and `MessageMatcherDelegatingAuthorizationManager`, plus the builder config matching your Spring Security version. **Do not paste it alone expecting a full STOMP system to run:** you still need `@EnableWebSocketMessageBroker`, `registerStompEndpoints`, `configureMessageBroker`, and explicit rules for `CONNECT`/`DISCONNECT`/`HEARTBEAT`, since a catch-all `denyAll` can block control messages unless permitted appropriately. Destination patterns must match your app prefixes and user-destination semantics.

**Key takeaway:** Both `SUBSCRIBE` and `SEND` can be sensitive operations. Restricting `/app/admin/**` only at the HTTP handshake does not stop an already-connected user from sending STOMP `SUBSCRIBE /topic/admin` if message security is missing. Define and test policies on both inbound and outbound destinations, tenant ownership, and subscriptions.

### 9.2. CSRF Token in STOMP CONNECT

With STOMP, browsers cannot attach arbitrary HTTP headers to the WebSocket handshake, yet a STOMP JavaScript client can place **STOMP CONNECT headers** inside the frame once the socket opens. Conceptual example:

```javascript
// Pseudocode for a properly initialized STOMP client.
// csrfHeaderName and csrfToken are fetched from a same-origin
// endpoint/meta tag after login.
stompClient.connect(
  { [csrfHeaderName]: csrfToken },
  () => console.log("STOMP connected")
);
```

Exact API syntax depends on the STOMP client version; modern `@stomp/stompjs` uses `connectHeaders` and `Client.activate()` rather than legacy `connect`. Never expose tokens cross-origin via wildcard CORS; ensure CSRF tokens are issued only to the rightful browser/session and never logged.

For SockJS fallbacks, some transports use HTTP POST; Spring Security advises **exempting HTTP CSRF only on a narrow matcher for SockJS transport URLs** when needed, because CSRF is verified at the STOMP CONNECT layer instead. That **never means disabling CSRF application-wide**. Follow the docs for your exact stack, transport, and version, verifying Origin restrictions and STOMP CONNECT CSRF stay enforced.

### 9.3. Token-Based STOMP Authentication

If mobile/SPA clients need bearer auth in STOMP `CONNECT`:

- Use a `ChannelInterceptor` to read CONNECT headers and verify the token via a standard authentication provider/JWT decoder.
- Once verified, attach the valid `Principal`/Authentication to the accessor/session per Spring Messaging APIs, ensuring the interceptor **runs before** the security authorization interceptor.
- Never trust a client-sent token without checking signature, expiration, audience, issuer, and scope.
- Plan for expiry/revocation during long-lived connections; authenticating at CONNECT does not keep a token valid forever.
- Never drop an auth token into a STOMP header assuming `Spring Security HTTP Bearer filter` will automatically inspect it—those are **two separate layers**.

Distinguish **cookie-authenticated browser STOMP** (inheriting the HTTP handshake principal) from **token-authenticated STOMP CONNECT** (custom token verification). Combining both without explicit precedence rules risks confused-deputy or identity mismatches.

## 10. Reverse Proxies, TLS, and Public Origin in Production

Browsers normally connect to:

```text
Page:       https://app.example.com/app
WebSocket:  wss://app.example.com/ws/echo
Origin:     https://app.example.com
```

Yet Spring Boot may listen on **internal HTTP** at `127.0.0.1:8080` behind an Nginx/gateway terminating TLS. You must configure:

- Proper `Upgrade` and `Connection` forwarding in the HTTP/1.1 WebSocket path.
- Ensuring the proxy preserves browser-sent `Origin`; if any rewrite occurs, govern it with **trusted, audited** rules.
- Exposing public scheme/host to Spring if the app generates links, redirects, or cookies from request metadata.
- Allowed origin **must be the public HTTP(S) origin** `https://app.example.com`, never `http://127.0.0.1:8080` or `wss://app.example.com`.
- Session cookie domain/path/Secure/SameSite must match the public HTTPS URL.
- The backend port must sit inside a private/trusted network; never let internet clients bypass the reverse proxy and spoof `X-Forwarded-*`.

**Illustrative** Nginx snippet for an HTTP/1.1 WebSocket Upgrade path:

```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8080/ws/;
    proxy_http_version 1.1;

    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    proxy_set_header Host app.example.com;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host app.example.com;
    proxy_set_header X-Forwarded-Port 443;

    # Long-lived WebSocket: timeout must align with ping/heartbeat.
    proxy_read_timeout 120s;
}
```

This snippet covers only the `location` block; you still need server TLS/certificates, host allowlists, network isolation, and full proxy configuration. `127.0.0.1` applies only when Nginx and Spring Boot share a network namespace; across separate containers, use private service DNS.

`proxy_read_timeout 120s` does not keep connections alive forever: without regular traffic/heartbeats, the proxy closes idle sockets. Coordinate server/session idle timeouts, TCP/WebSocket ping/pong or STOMP heartbeats, and intermediary timeouts.

**Beware header poisoning:** `Origin` and `X-Forwarded-Host` serve different purposes. `X-Forwarded-Host` must be **controlled by trusted proxies**—never trust client-supplied forwarded headers to construct absolute URLs, redirects, or security decisions. Origin checks compare against registered public origins. Never mask a proxy header or cookie misconfiguration by flipping `setAllowedOrigins("*")` to bypass a 403.

### 10.1. WebSocket and HTTP/2 at the Proxy

A CDN/edge may serve the page over HTTP/2 while converting WebSocket to HTTP/1.1 Upgrade on an inner hop. Never assume an HTTP/2 website automatically runs WebSocket over Extended CONNECT. Check every hop and server's support:

- Browser ↔ CDN/gateway.
- Gateway ↔ Nginx/ingress.
- Nginx/ingress ↔ embedded server.

If a client uses WebSocket over HTTP/2 Extended CONNECT, the proxy must support RFC 8441 on that hop; never copy HTTP/1.1 `Connection: Upgrade` onto HTTP/2. Test real handshakes over the public URL, not just localhost.

## 11. Token Authentication: Choices and Trade-Offs

| Client/Mechanism | How Credentials Enter the Connection | Special Considerations |
| --- | --- | --- |
| Browser with form/OAuth2 login | Session cookie sent automatically in HTTP handshake | Origin allowlist, CSWSH, SameSite/Secure, HTTP session lifecycle |
| Native/mobile client | `Authorization: Bearer ...` in handshake when supported by client | HTTPS/WSS, JWT validation, expiry, and audience |
| Browser + STOMP token | Token in STOMP `CONNECT` frame, custom `ChannelInterceptor` | CONNECT runs **after** HTTP handshake; message auth must verify token before allowing actions |
| Browser + short-lived one-time ticket | Ticket issued by backend over HTTPS, scoped tightly | Avoid URL logging, very short TTL, audience binding, single-use/replay defense |
| Basic authentication | Credentials in HTTP handshake from supporting clients | Browser JS WebSocket lacks arbitrary Authorization header control; enforce HTTPS and rate limits |
| Mutual TLS or proxy auth | Identity asserted by trusted transport/proxy | Never trust an arbitrary client-supplied `X-User` header from the internet |

**Do not put long-lived JWTs in URLs** for "simplicity". Never pass credentials inside user-supplied query strings where URLs get cached and logged. When using signed tickets, define the issuing authority, short TTL, single-use guarantee, origin/rate limits, and mid-connection expiry handling.

### When User Permissions Change or User Logs Out While the Socket Is Open

The HTTP session/auth at handshake time usually sets the WebSocket `Principal`. Yet account state can change:

```text
09:00: user demo connects with ROLE_USER
09:05: admin disables user
09:06: old socket stays open unless the app actively handles it
```

Define an explicit contract:

- **Per-message revalidation** for sensitive operations (checking current permissions/tenant from an authoritative source).
- **Connection registry** to terminate all sockets belonging to a principal on revocation/logout.
- **Maximum session lifetime / token expiry** forcing reconnect.
- **STOMP SUBSCRIBE authorization** per destination/room.
- **Backpressure and message quotas** preventing one user from holding excessive sockets.
- **Spring Session WebSocket** integration if using HTTP sessions and needing session store events/timeout propagation.

Never check only `session.getPrincipal() != null` on every message and treat it as eternal valid authentication.

## 12. WebSocket Session, HTTP Session, and Concurrency

| Object | Scope | Automatically Means Logged-In User? |
| --- | --- | --- |
| HTTP `HttpSession` | Multiple HTTP requests sharing session ID/cookie | No; may be an anonymous session |
| Spring Security `Authentication` | Verified identity per filter/security context | Represents authentication, yet authorization checks are still required |
| `WebSocketSession` | Single WebSocket connection with ID/attributes/Principal | Does not authenticate by itself; Principal comes from handshake or custom logic |
| STOMP session | Messaging-layer logical session over transport | Requires explicit `CONNECT`, `SEND`, `SUBSCRIBE` policies |

One HTTP session can back **multiple WebSocket sessions** (multiple tabs), each with its own connection lifecycle. Logging out in one tab does not guarantee other WebSocket sessions close instantaneously without explicit integration.

### 12.1. Managing Write Concurrency

With Spring `WebSocketSession`, multiple threads calling `sendMessage(...)` on the same session concurrently is not always safe. When publishers or broadcast listeners can send simultaneously, serialize writes or wrap with Spring's `ConcurrentWebSocketSessionDecorator` enforcing send time and buffer limits:

```java
// Illustrative snippet when the app manages multiple writers:
// new ConcurrentWebSocketSessionDecorator(
//     originalSession, sendTimeLimitMillis, bufferSizeLimitBytes
// );
```

Size limits according to message payloads and client counts; avoid queuing thousands of unsent messages, as a slow client can drive server memory upward without bound.

### 12.2. Heartbeats and Timeouts

WebSocket has protocol-level Ping/Pong frames; STOMP has its own `heart-beat` semantics. Browser WebSocket APIs do not expose arbitrary Ping/Pong sending from JavaScript like custom app messages, so servers/proxies may need explicit heartbeat policies.

- Send heartbeats at an interval tailored to keep connections alive across idle timeouts.
- Never confuse "TCP connection still open" with "user is still active or authorized".
- Implement client reconnect exponential backoff + jitter to avoid thundering herds on server restarts.
- Enforce opening handshake timeouts, max sessions/user, max text/binary payloads, throttling, rate limits, and idle close policies.
- Log `connected/disconnected/error` events with non-sensitive request/connection IDs; never log session cookies or raw tokens.

### 12.3. Rejecting Messages After Handshake

Once a WebSocket request receives 101, the HTTP filter chain no longer runs per frame. Consider a message:

```json
{"type":"DELETE_INVOICE","invoiceId":"123"}
```

The handler must **parse against a strict schema**, verify the user, check permission to delete invoice 123 by tenant/owner, and enforce replay defenses if needed. If unauthorized:

- Do not execute the action.
- Optionally return a protocol-level application error message.
- Optionally close the WebSocket with code `1008` per app policy.
- Never claim to return "HTTP 403" as a response body for a WebSocket message after `101`.

With STOMP, enforce destination and business-object authorization in the messaging/service layer; having `hasRole("USER")` on the HTTP handshake does not protect inner operations.

## 13. Common Mistakes to Watch For

**Mistake 1 — Relying on REST CORS to protect WebSocket.** `@CrossOrigin` on an HTTP controller does not configure allowed origins on `WebSocketHandlerRegistry`. Configure `setAllowedOrigins` or the STOMP endpoint directly.

**Mistake 2 — `setAllowedOrigins("*")` on cookie-authenticated sockets.** Widens CSWSH exposure. Allow only operator-managed public origins; never echo back origins from incoming requests.

**Mistake 3 — Treating `Origin` as proof of identity.** Non-browser clients can set arbitrary headers; auth must rely on verified credentials.

**Mistake 4 — Allowing anonymous handshakes and trusting client-sent usernames.** `{"user":"admin"}` inside a message does not authenticate an admin. Use the Principal from the HTTP handshake or validated CONNECT token, and authorize every action.

**Mistake 5 — Checking only HTTP `authenticated()` and skipping message-level authorization.** Open connections can send arbitrary commands unless business code enforces schema/destination/room/action ownership.

**Mistake 6 — Trying to pass `Authorization` headers in Browser WebSocket API like `fetch`.** `new WebSocket(url, protocols)` does not accept arbitrary headers. Use session cookies or a token scheme designed for your stack and threat model.

**Mistake 7 — Putting long-lived JWTs in query strings.** Tokens leak into proxy logs and tracing; choose another approach, or a tightly constrained short-lived single-use ticket if unavoidable.

**Mistake 8 — Applying STOMP `CONNECT` CSRF rules to raw `TextWebSocketHandler`.** They are different stacks; raw WS has no STOMP CONNECT. Rely on Origin checks, HTTP/handler auth, and a custom app message protocol.

**Mistake 9 — Disabling CSRF globally because login POST returned 403.** HTTP form CSRF and STOMP CONNECT CSRF protect different layers. Supply the proper token rather than turning off CSRF.

**Mistake 10 — Using `ws://` on an HTTPS page.** Use `wss://` with proper proxy/TLS; never downgrade browser security to make a handshake work.

**Mistake 11 — Wrong public Origin behind a reverse proxy.** Internal `localhost:8080` is not the browser's public origin. Allowlist `https://app.example.com`, never `wss://app.example.com`.

**Mistake 12 — Testing with plain `curl GET` without Upgrade and concluding auth failed.** Missing handshake headers cause HTTP 400; test with a real WebSocket client and verify filter ordering.

**Mistake 13 — Trying to return HTTP 401/403 per message after 101.** Post-handshake traffic consists of WebSocket frames; use close codes or app-level errors while checking principal/permissions.

**Mistake 14 — Failing to update user permissions on open sockets.** Logout/revocation does not always close open sockets immediately; implement registries, TTLs, or revalidation.

**Mistake 15 — Echoing HTML into `innerHTML`.** Data arriving over sockets remains untrusted; render via `textContent` or context-appropriate escaping.

**Mistake 16 — Leaving message sizes or concurrent writes unbounded.** Slow clients or large payloads can exhaust memory or break sessions. Bound sizes, buffers, throughput, concurrent sends, and backpressure.

**Mistake 17 — Confusing `Origin` with `Sec-WebSocket-Protocol`.** Origin identifies the initiating page; subprotocol names a layered protocol like STOMP. Neither verifies user identity.

**Mistake 18 — Forgetting one HTTP session can spawn many WebSocket connections.** Multiple tabs and reconnects create multiple sessions; enforce per-user quotas, cleanup, and policies.

## 14. Diagnostic Guide by Status and Event

| Symptom | Check First | Resolution |
| --- | --- | --- |
| `302 /login` on handshake | Does the user have a valid authenticated cookie/session? | Log in via HTTP first; check cookie/path/session |
| `401` + challenge | Is entry point Basic/Bearer? Missing/invalid credential? | Use the expected auth scheme rather than parsing HTML |
| `403` before 101 | Origin mismatch, security rule, CSRF, or gateway? | Isolate the rejecting layer via logs and authenticated handshake test |
| `400` handshake | Are `Upgrade`, `Connection`, version, key, subprotocol valid? | Use a WebSocket-aware client |
| `404` only in production | Wrong proxy path rewrite, context path, or endpoint mapping? | Inspect `/ws/echo` routing through ingress |
| Browser says `WebSocket connection failed` | DevTools → Network WS, server logs, edge logs | Do not expect JS `onerror` to expose full response details |
| `101` received yet messages never return | Handler, authorization, payload limit, or serialization issue? | Inspect Frames, close code, and logs |
| Disconnect code `1009` | Payload exceeded limit | Adjust contract/limits rather than setting them unbounded |
| Disconnect code `1008` | Policy violation, insufficient permissions | Check auth/tenant/message policy |
| Socket drops after idle period | Proxy/network/server idle timeout | Tune heartbeats/Ping/Pong and `proxy_read_timeout` |
| Works on HTTP, fails only on HTTPS | Cookie Secure/SameSite, WS vs. WSS, trusted proxy headers | Fix public TLS URL and origin allowlist |
| Messages still go through after logout | Old connection not revoked/closed | Implement connection revocation and per-message checks |
| Origin test fails in MockMvc | Was the request authenticated before reaching the interceptor? | Test Origin policy separately from authentication |
| STOMP CONNECT fails security | Are CONNECT CSRF and message authorization configured properly? | Inspect STOMP headers and Spring Messaging config |
| User connects yet subscribes to someone else's private room | Missing message-level/object authorization | Validate `SUBSCRIBE` destination and tenant/owner |

## 15. Pre-Production Testing Checklist

- [ ] Maintain an exact allowlist of public HTTP(S) origins; never use `*` when sockets rely on cookies.
- [ ] Cover WebSocket endpoints in `SecurityFilterChain`, avoiding accidental `permitAll` on sensitive sockets.
- [ ] Anonymous handshakes are rejected per entry point (302/401), never receiving 101.
- [ ] Authenticated users from allowed origins upgrade with 101 over the **public WSS URL**.
- [ ] Authenticated users with disallowed Origins **do not** receive 101.
- [ ] Because non-browser clients can spoof Origin, business messages still enforce auth/authorization.
- [ ] Requests missing or having invalid WebSocket version/key/upgrade headers are rejected per protocol.
- [ ] Browser session cookies enforce `Secure`/`HttpOnly`/`SameSite`/`Path`/`Domain` and never appear in logs.
- [ ] HTTP login/logout forms include CSRF tokens; STOMP setups verify `CONNECT` CSRF when Spring Security messaging is enabled.
- [ ] Session `Principal` is server-verified, never read from message username strings.
- [ ] Message schemas, tenant/room/resource ownership, and subscription policies are checked per action.
- [ ] Clear policies handle logout, account disablement, token expiry, and privilege revocation mid-socket.
- [ ] WebSocket text/data renders safely (DOM `textContent`), never building HTML from user data.
- [ ] Message/frame/buffer sizes, per-user connections, rates/timeouts/backpressure, and concurrent sends are bounded.
- [ ] Proxies support Upgrade, public URLs, Origin, WSS, idle timeouts/heartbeats, and session stickiness/stores.
- [ ] Metrics track active sockets, accepted/rejected handshakes, close codes, abnormal closes, reconnect spikes, and error rates.
- [ ] Tested HTTP handshake rejection, post-101 message authorization, SockJS/STOMP if used, and real ingress routing.
- [ ] Spring Boot/Framework/Security run patched, supported versions without exposing backend ports directly to the internet.

## 16. Self-Check Questions

**Question 1.** Do `Origin: https://app.example.com` and WebSocket URL `wss://app.example.com/ws` contradict each other?  
**Answer:** No. Origin is the HTTP(S) origin of the page; the target WebSocket URL uses ws/wss.

**Question 2.** Why isn't `Origin` authentication?  
**Answer:** Non-browser clients can set `Origin` arbitrarily, whereas credentials must be verified by the server from a session, token, or authentication mechanism.

**Question 3.** Why can a malicious site attempt to open a WebSocket to a logged-in website?  
**Answer:** WebSocket does not rely on CORS preflight like fetch, and browsers can attach cookies per policy. Servers must reject non-allowlisted Origins and enforce authentication.

**Question 4.** Why might a WebSocket handshake receive 302 `/login` instead of 401?  
**Answer:** The app uses Spring Security form login with a redirect entry point. WebSocket clients fail the upgrade whenever they do not receive 101.

**Question 5.** Is `Sec-WebSocket-Key` a bearer token?  
**Answer:** No; it is an RFC 6455 handshake nonce and does not verify user identity.

**Question 6.** Does `@CrossOrigin` on a REST controller secure WebSocket same-origin policy?  
**Answer:** No. Configure `WebSocketHandlerRegistry.setAllowedOrigins` or the STOMP endpoint separately.

**Question 7.** After 101, does each WebSocket message pass through the HTTP `SecurityFilterChain`?  
**Answer:** Not as a new HTTP request. Enforce authorization at the handler or message layer.

**Question 8.** Does STOMP CONNECT CSRF apply automatically to raw `TextWebSocketHandler`?  
**Answer:** No. They are two separate messaging models.

**Question 9.** Does browser JS `new WebSocket(url)` support `headers: {Authorization: ...}`?  
**Answer:** No API exists to send arbitrary headers like fetch. Use session cookies or a protocol/auth architecture suited to your client.

**Question 10.** When a user logs out, do open sockets close immediately on their own?  
**Answer:** Not guaranteed; coordinate session lifecycles with connection revocation and revalidation.

**Question 11.** Can an unauthorized message after 101 return a standard HTTP 403?  
**Answer:** No; send an application error or a WebSocket Close frame such as 1008.

**Question 12.** Why isn't a MockMvc GET test sufficient to prove WebSocket works?  
**Answer:** MockMvc does not test real HTTP Upgrades, frames, cookies, or proxies; test with a real WebSocket client/browser against a live server.

**Question 13.** Should authentication and Origin be tested separately?  
**Answer:** Yes. Unauthenticated requests may be rejected by security filters before the Origin check runs; verifying Origin checks requires an authenticated request.

**Question 14.** If using STOMP CONNECT tokens instead of cookies, what else is required?  
**Answer:** Verify tokens in a `ChannelInterceptor` before message authorization, handle CSRF/origin per architecture, and authorize `SEND`/`SUBSCRIBE`.

## 17. Official Documentation

- Spring Framework 6.2 — **WebSocket API, Handshake and Allowed Origins**: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/server.html
- Spring Framework — **WebSocket STOMP Overview**: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html
- Spring Framework 6.2 — **Token Authentication over STOMP**: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authentication-token-based.html
- Spring Security 6.5 — **WebSocket Security, Authentication, Authorization and STOMP CSRF**: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html
- Spring Security 6.5 — **CSRF for HTTP Forms**: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 — **Form Login**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Boot — **WebSocket Support**: https://docs.spring.io/spring-boot/reference/messaging/websockets.html
- RFC 6455 — **The WebSocket Protocol** (handshake, frames, close codes): https://www.rfc-editor.org/rfc/rfc6455
- RFC 6454 — **The Web Origin Concept**: https://www.rfc-editor.org/rfc/rfc6454
- RFC 8441 — **Bootstrapping WebSockets with HTTP/2**: https://www.rfc-editor.org/rfc/rfc8441
- MDN — **WebSocket API**: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket
- Spring Boot 3.5.16 release/support notice: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Conclusion:** WebSocket must be protected both **before** and **after** the HTTP handshake. Before `101`, restrict Origin, authenticate the HTTP Principal, and upgrade only valid requests. After `101`, enforce permissions **per message and destination**, manage session/token expiry, payload limits, concurrency, and close codes. With STOMP, layer security on `CONNECT`/`SEND`/`SUBSCRIBE`, including CONNECT CSRF when Spring Security messaging is enabled. Never treat Origin as authentication, never expect HTTP filters to guard individual frames, and test both the live server and the WSS reverse proxy.
