# HandshakeInterceptor, Origin Checking, and User Identity in WebSocket/STOMP

## 1. Context: What Must WebSocket Verify Before Upgrading a Connection?

In a Spring application, browsers can open a WebSocket connection to exchange real-time data: chat, notifications, or status updates. Unlike a standard HTTP request, a WebSocket connection can stay open for a long time and transmit many messages in both directions. If you mistakenly accept a connection from an untrusted website or bind the wrong user, the impact goes beyond a single response: an attacker can send and receive messages over a long-lived session.

The phase begins with an HTTP *handshake* request. The server evaluates the connection conditions and only then agrees to upgrade to WebSocket (on success, the typical HTTP status is **101 Switching Protocols**). If the application uses STOMP, the client subsequently sends a STOMP `CONNECT` frame over the established connection; only from that point onward do `SUBSCRIBE`, `SEND`, and other business frames occur.

```text
Browser                             Spring WebSocket/STOMP server
     |                                            |
     |-- HTTP GET /ws, Upgrade: websocket ------->|
     |   Origin: https://app.example.com          |
     |   Cookie: login session (if any)           |
     |                                            v
     |                             HTTP security filter chain
     |                                            |
     |                             HandshakeInterceptor.beforeHandshake
     |                                  | inspect request/Principal
     |                                  | attach session attributes
     |                                            |
     |                             check Origin and handshake handler
     |                                  |
     |<-------------- HTTP 101 (if accepted)      |
     |                                            |
     |--------- STOMP CONNECT frame ------------->|
     |                             clientInboundChannel:
     |                             ChannelInterceptor / STOMP security
     |<------------- STOMP CONNECTED -------------|
     |--------- STOMP SUBSCRIBE / SEND ---------->|
     |                             check per-message/destination permissions
```

Three distinct questions:

1. **Is the Origin accepted?** Origin indicates the web page origin that initiated the connection in a browser context; this check helps defend against unauthorized WebSocket connections opened from another website.
2. **Who is the user?** On the HTTP handshake path, the application has usually already authenticated via Spring Security/session or an equivalent HTTP mechanism; the authenticated `Principal` can be associated with the WebSocket session.
3. **Which messages is the user allowed to send or subscribe to?** This is per-frame/per-destination access control in STOMP, and **must not be skipped just because the handshake succeeded**.

`HandshakeInterceptor` is suited for observing and preparing the handshake, allowing early rejection or passing metadata into the WebSocket session. It does not replace HTTP authentication, Origin policy, or message authorization checks.

## 2. Distinguishing Spring Components

| Component | When does it run? | Role |
| --- | --- | --- |
| `SecurityFilterChain` (Servlet) | When the HTTP request enters, before upgrade | HTTP authentication, endpoint access authorization, appropriate CSRF/header policies |
| `HandshakeInterceptor` | Before and after handshake processing | Inspect request, reject handshake, add attributes to the WebSocket session |
| `HandshakeHandler` / `DefaultHandshakeHandler` | During HTTP upgrade negotiation | Check upgrade capability, configured Origin, subprotocol, and determine Principal |
| `WebSocketSession` | After WebSocket is opened | Represents a connection, ID, headers, attributes, and Principal |
| `ChannelInterceptor` | When processing messages on a channel like `clientInboundChannel` | Read/control STOMP `CONNECT`, `SEND`, `SUBSCRIBE`, and corresponding frames |
| Spring Security message authorization | In the inbound STOMP message processing chain | Decide who can send to or subscribe to which destination |
| `@MessageMapping` / `@SendTo` | When a STOMP message is dispatched to a controller | Business processing, sending responses to broker/destination |

Do not confuse `HandshakeInterceptor` with `HandlerInterceptor` for regular HTTP MVC requests. Also do not confuse raw WebSocket handlers (`WebSocketConfigurer` and `WebSocketHandler`) with STOMP endpoints (`WebSocketMessageBrokerConfigurer` and `StompEndpointRegistry`).

### 2.1 HandshakeInterceptor Contract

The interface has two callbacks:

```java
boolean beforeHandshake(
        ServerHttpRequest request,
        ServerHttpResponse response,
        WebSocketHandler wsHandler,
        Map<String, Object> attributes) throws Exception;

void afterHandshake(
        ServerHttpRequest request,
        ServerHttpResponse response,
        WebSocketHandler wsHandler,
        Exception exception);
```

- `beforeHandshake` receives the HTTP request/response, target handler, and the WebSocket session attributes map. **Return `true`** to proceed with the handshake; **return `false`** to block it. When blocking, you can set a status (such as 401 or 403) on the response before returning `false`.
- The `attributes` map is **copied** by Spring into the session, rather than reusing the exact map reference passed to the interceptor. Store small, stable values; do not use it as a channel for secret credentials or objects holding unreleased resources.
- `afterHandshake` runs after the handshake step to observe the outcome or any exception. It cannot "return true" to revive a rejected handshake and **is not a callback invoked after every STOMP message**.
- The `WebSocketHandler` parameter is the handler configured for the endpoint; in a STOMP application, Spring uses subprotocol-handling infrastructure behind this endpoint.

Do not use `attributes.put("user", "alice")` to fabricate a `Principal` or elevate privileges for a connection. Attributes are merely session metadata; identity and authentication must come from a trusted security component.

## 3. Origin Checking: Rationale, Configuration, and Limitations

### 3.1 Origin is not the same as Host, Referer, or regular CORS

For example, a page at `https://app.example.com` opens `wss://api.example.com/ws`. The browser's HTTP WebSocket handshake may carry:

```http
GET /ws HTTP/1.1
Host: api.example.com
Upgrade: websocket
Connection: Upgrade
Origin: https://app.example.com
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: <value used for handshake>
```

`Origin` reflects the calling page's origin (scheme + host + port), not the target server's URL and not `Referer`. For server/CLI tools, the `Origin` header can be arbitrarily set or spoofed. Therefore, Origin checking protects against **browser-based** threats and is insufficient for authenticating users or protecting APIs from custom clients.

Browsers do not apply the exact same-origin restriction of XHR/fetch to block cross-origin WebSocket connections. The server must decide which Origins are permitted, especially when credentials are sent via cookies (**Cross-Site WebSocket Hijacking**, or CSWSH risk).

### 3.2 Recommended approach: setAllowedOrigins on the endpoint

In Spring STOMP, configure the allowed Origins directly on the endpoint:

```java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.com");
}
```

This is a method snippet inside a class implementing `WebSocketMessageBrokerConfigurer`, not a standalone file. Spring supports Origin validation during the handshake; by default, WebSocket/SockJS only allows same-origin requests. You can specify an explicit list of origins via `setAllowedOrigins(...)`, or use `setAllowedOriginPatterns(...)` when patterns are truly needed and their scope has been evaluated.

Rules:

- Specify the **full origin** including scheme, host, and port when needed—for example `http://localhost:5173` in development and `https://app.example.com` in production. Do not include a path like `/dashboard` in the origin list.
- `https://app.example.com` and `http://app.example.com` are two distinct origins; non-default ports also create distinct origins.
- Avoid `setAllowedOrigins("*")` on endpoints authenticated with cookies or carrying sensitive data. Allowing all Origins removes an important browser-layer defense.
- Behind a reverse proxy, ensure scheme/host are resolved correctly via forwarded headers **only from trusted proxies**. Otherwise, comparing Origin against the externally visible endpoint may fail or be misinterpreted.
- If `withSockJS()` is enabled, changing the allowed Origins list also affects fallback transports; some mechanisms such as iframe transports may be disabled when origin restrictions are active.

There is no need to reimplement Origin matching inside `HandshakeInterceptor` when the default rules and `setAllowedOrigins` already suffice. An interceptor can still enforce supplemental policies, such as checking a server-side tenant subscription or rejecting unauthenticated secure connections.

### 3.3 Why are Origin and CSRF related yet different?

Origin restricts which websites can initiate a WebSocket from a browser. CSRF protects against actions that exploit automatically sent credentials (such as session cookies) while a user is logged in.

When enabling Spring Security for STOMP, the security configuration may also require a **CSRF token in the STOMP `CONNECT` frame**, providing messaging-layer protection. Depending on the version and security setup, sending CONNECT without the token can be rejected even though the HTTP handshake succeeded. Especially with SockJS fallback, some transports use HTTP POST; do not solve this by disabling CSRF globally across the application. If HTTP exceptions are required for SockJS to work, scope them tightly to the SockJS URLs and continue enforcing STOMP-level security.

**Common mistake:** "Once `setAllowedOrigins` is configured, message authorization is unnecessary." Origin does not determine which user may `SUBSCRIBE /topic/private` or `SEND /app/admin`. You must configure message-level policies based on a trusted `Principal`/`Authentication`.

## 4. Authentication and User Identity During the Handshake

### 4.1 Using the authenticated Principal from the HTTP request

Common case: a user has logged in via HTTP/Spring Security; when the browser opens a WebSocket, the handshake request carries the site's session cookie. Spring extracts the authenticated `Principal` from the HTTP request and attaches it to the WebSocket/STOMP session. Message controllers can then accept `Principal` as a parameter.

```text
HTTP login / trusted session authentication
    |
    v
SecurityFilterChain authenticates GET /ws request
    |
    v
request.getPrincipal()  ---> DefaultHandshakeHandler
    |                                 |
    |                                 v
    |                         WebSocket Principal
    |                                 |
    v                                 v
HandshakeInterceptor              STOMP message "user"
    |
    +--> session attributes (additional metadata)
```

Never trust a `userId` from a query string `?user=alice`, any client-supplied header, or the native STOMP `login` header to determine the `Principal` of an HTTP-authenticated request.

In Spring's default STOMP configuration, the `login` and `passcode` headers in the CONNECT frame are not used to re-authenticate the WebSocket user: Spring takes the identity from the HTTP handshake. If an application passes a separate bearer token in STOMP CONNECT (common when browsers cannot attach custom HTTP Authorization headers in the WebSocket API), you need a `ChannelInterceptor` on `clientInboundChannel` to read the token, validate it server-side, and set `accessor.setUser(authentication)` per Spring's rules; that happens **after the handshake**, not inside `HandshakeInterceptor`.

### 4.2 Writing a HandshakeInterceptor to reject anonymous requests and attach metadata

The following example intentionally does not perform username/password validation inside the interceptor itself. It assumes the HTTP security chain has already authenticated requests to `/ws`. If no valid principal exists, the request is rejected. The `connectedUserId` attribute is only for session cross-checking; actual permissions remain grounded in `Principal`.

**File `VerifiedUserHandshakeInterceptor.java`:**

```java
package com.example.websocket;

import java.security.Principal;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

public final class VerifiedUserHandshakeInterceptor
        implements HandshakeInterceptor {

    public static final String USER_ID = "connectedUserId";

    @Override
    public boolean beforeHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Map<String, Object> attributes) {

        Principal principal = request.getPrincipal();

        if (principal == null
                || principal.getName() == null
                || principal.getName().isBlank()) {
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return false;
        }

        attributes.put(USER_ID, principal.getName());
        return true;
    }

    @Override
    public void afterHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Exception exception) {
        // Intentionally empty: no post-handshake processing needed for this example.
    }
}
```

This is complete Java 17+ code for a class used in a Spring WebSocket project. If the project uses Spring Security, ensure **the handshake endpoint is protected by HTTP security**: in many configurations, an `AnonymousAuthenticationToken` may be present in the SecurityContext even when the user has not logged in; do not rely solely on whether a `Principal` object has a name to define authentication across all setups. Primary authentication/authorization policy should live in `SecurityFilterChain`, while this example interceptor acts as a secondary check and copies metadata after authentication.

**Important point:** `attributes.put(USER_ID, principal.getName())` does not change the WebSocket session's `Principal`. `DefaultHandshakeHandler` and Spring infrastructure manage `Principal` selection. If custom identity mapping beyond the default HTTP mechanism is needed, use a verified strategy and integrate properly via `HandshakeHandler.determineUser(...)` or a STOMP `ChannelInterceptor`—never assign usernames from untrusted input.

### 4.3 What should and should not be stored in attributes

Appropriate: incident correlation IDs, verified tenant IDs, connection timestamps, protocol version markers, or small technical flags. Inappropriate: passwords, raw JWTs, refresh tokens, entire mutable `SecurityContext` objects, raw cookies, sensitive bodies, or connection/database handles.

The attributes map shares the WebSocket session's lifecycle; connections can live much longer than HTTP requests. Keep the count and size of entries small, with cleanup plans and proper access policies.

## 5. Complete STOMP Endpoint Configuration Example

**File `WebSocketStompConfig.java`**:

```java
package com.example.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketStompConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .addInterceptors(new VerifiedUserHandshakeInterceptor())
                .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

Explanation of each part:

- `@EnableWebSocketMessageBroker` enables STOMP over WebSocket infrastructure.
- `/ws` is the **HTTP handshake** path; it is not a destination that clients `SUBSCRIBE` or `SEND` to.
- `addInterceptors(...)` registers the `HandshakeInterceptor` during the HTTP handshake step.
- `setAllowedOrigins(...)` requires the page's Origin to be in the allowed list.
- `/app` is the prefix for messages routed to `@MessageMapping`; `/topic` and `/queue` are managed by the simple broker in this example.

In a Servlet application using Spring Security, protect the endpoint with an appropriate HTTP security chain. The snippet below assumes `spring-boot-starter-security` is present and web authentication is configured (login/session or another mechanism):

**File `WebHttpSecurityConfig.java`:**

```java
package com.example.websocket;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class WebHttpSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/ws", "/ws/**").authenticated()
                .anyRequest().permitAll());
        http.formLogin(withDefaults());
        return http.build();
    }
}
```

**Scope note:** this example targets Spring MVC/Servlet + Spring Security 6, where the HTTP handshake goes through the Servlet security chain; it is not a reactive Spring WebFlux `SecurityFilterChain` configuration. `anyRequest().permitAll()` is only a placeholder to focus on the dedicated endpoint; in a real product, use your system's existing HTTP policy and never leave sensitive routes open. This sample config does not disable CSRF and does not blindly grant STOMP permissions; when enabling WebSocket message security, configure authorization and CONNECT CSRF accordingly.

For Spring Boot 3.x/Java 17+, the Gradle setup in the project uses Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Spring Boot 3.3.x in the learning module typically uses Java 21, though this code is Java 17+ compatible. Place the three classes in package `com.example.websocket` beneath the Spring Boot application's root package so component scanning picks up `@Configuration`. This example uses an illustrative domain; cross-origin connections from sites other than `https://app.example.com` will be rejected by the endpoint's Origin check. Create real accounts and authentication per application policy; never hardcode production usernames or passwords in documentation.

## 6. Reading User Identity and Session Attributes in a STOMP Message Controller

After the handshake succeeds and a STOMP client sends a message, the application can read both `Principal` and session attributes inside a `@MessageMapping` method. These two sources differ: `Principal` is the identity bound to the session by Spring; attributes are extra data created during the handshake.

**File `IdentityMessageController.java`:**

```java
package com.example.websocket;

import java.security.Principal;
import java.util.Map;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class IdentityMessageController {

    @MessageMapping("/whoami")
    @SendToUser("/queue/identity")
    public String whoAmI(
            Principal principal,
            SimpMessageHeaderAccessor headers) {

        Map<String, Object> attributes = headers.getSessionAttributes();
        Object copiedUser = attributes == null
                ? null
                : attributes.get(VerifiedUserHandshakeInterceptor.USER_ID);

        // Demo: return only the authenticated username.
        // Session metadata is used only for observation/cross-checking.
        if (principal == null) {
            throw new IllegalStateException("Authenticated user required");
        }

        String verifiedName = principal.getName();
        if (copiedUser != null
                && !verifiedName.equals(copiedUser.toString())) {
            throw new IllegalStateException("Session identity mismatch");
        }
        return verifiedName;
    }
}
```

An authenticated STOMP client can send a message to `/app/whoami` and listen on the corresponding user destination such as `/user/queue/identity`, depending on broker and messaging security configuration. The returned value is the authenticated username; do not return secrets.

Here, comparing the two fields only serves to **detect inconsistent metadata** in a learning example. Access-control decisions must still rely on `Authentication`/`Principal` and server-side policy, not on a value in session attributes alone. When identity can change during a connection's lifetime, the design must handle session rotation, token expiration, account locking, and explicit connection closure policies.

### 6.1 Distinguishing connection, user, and subscription

- One account can open **multiple WebSocket sessions** (multiple tabs or devices), so do not treat a username as a unique connection ID.
- `sessionId` is assigned by Spring to a single WebSocket/STOMP session; the user principal name identifies the user per the authentication mechanism.
- `attributes` can hold supplemental per-connection metadata.
- One STOMP session can hold multiple subscriptions; `SUBSCRIBE` permissions must be checked based on destination and user, never solely on "handshake succeeded".
- `SimpUserRegistry` and `/user` infrastructure help Spring route messages by user/session; do not assume each user has exactly one socket.

## 7. If the Token Is in STOMP CONNECT, Can HandshakeInterceptor Read It?

**No.** The HTTP handshake occurs **before** the STOMP `CONNECT` frame exists. `HandshakeInterceptor` only sees the HTTP request (cookies, Origin, HTTP-layer headers) and cannot read native headers from a STOMP frame that has not been sent yet.

Browser applications typically have these options:

1. **Session/cookie authentication at HTTP handshake:** Spring Security authenticates the request; Spring propagates the `Principal` to the WebSocket/STOMP session. Suitable when the site and WebSocket endpoint share the same login system.
2. **Token in STOMP CONNECT:** after the handshake, a `ChannelInterceptor` on `clientInboundChannel` reads the token header, calls a server-side authentication service, creates a valid `Authentication`, and calls `StompHeaderAccessor.setUser(...)` on CONNECT. Handle missing/invalid/expired tokens and enforce message authorization.
3. **Token/cookie on HTTP handshake:** with the browser `new WebSocket(...)` API, you cannot freely set arbitrary custom HTTP headers as with `fetch`. Avoid putting long-lived bearer tokens in URL query parameters since they leak into logs, browser history, and proxies; choose an architecturally sound mechanism with proper safeguards.

The following snippet illustrates the **structure** of a STOMP interceptor; token validation requires a trusted system service, so no mock check is written that might be mistaken for real authentication:

```java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new ChannelInterceptor() {
        @Override
        public Message<?> preSend(Message<?> message,
                                   MessageChannel channel) {
            StompHeaderAccessor accessor =
                    MessageHeaderAccessor.getAccessor(
                            message, StompHeaderAccessor.class);

            if (accessor != null
                    && StompCommand.CONNECT.equals(accessor.getCommand())) {
                // Extract token from native STOMP headers.
                // Validate token via an actual security service.
                // Only after authentication succeeds:
                // accessor.setUser(validatedAuthentication);
            }
            return message;
        }
    });
}
```

This is a *structural illustration fragment* inside a `WebSocketMessageBrokerConfigurer` class, **not standalone authentication logic**. Import `ChannelRegistration`, `ChannelInterceptor`, `Message`, `MessageChannel`, `MessageHeaderAccessor`, `StompHeaderAccessor`, and `StompCommand`. Never deploy this code as production security without implementing signature verification, expiration checks, user/permission validation, and connection rejection. With Spring Security messaging authorization, the CONNECT authentication interceptor must be ordered before the security authorization interceptor.

When using default HTTP authentication, Spring may ignore STOMP CONNECT's `login` and `passcode`. Never accept an arbitrary string in `login` and treat it as an authenticated username.

## 8. Testing HandshakeInterceptor Without a Real Network Server

Unit tests verify accept/reject rules for `Principal` and metadata without opening a real WebSocket. Use Mockito to mock `ServerHttpRequest`, `ServerHttpResponse`, and `WebSocketHandler`. The class below runs with JUnit 5 + `spring-boot-starter-test`.

**File `VerifiedUserHandshakeInterceptorTest.java`** in `src/test/java/com/example/websocket/`:

```java
package com.example.websocket;

import java.security.Principal;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.socket.WebSocketHandler;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class VerifiedUserHandshakeInterceptorTest {

    private final VerifiedUserHandshakeInterceptor interceptor =
            new VerifiedUserHandshakeInterceptor();

    @Test
    void rejectsHandshakeWithoutPrincipal() {
        ServerHttpRequest request = mock(ServerHttpRequest.class);
        ServerHttpResponse response = mock(ServerHttpResponse.class);
        WebSocketHandler handler = mock(WebSocketHandler.class);
        Map<String, Object> attributes = new HashMap<>();

        boolean proceed = interceptor.beforeHandshake(
                request, response, handler, attributes);

        assertFalse(proceed);
        assertTrue(attributes.isEmpty());
        verify(response).setStatusCode(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void acceptsTrustedPrincipalAndCopiesItsName() {
        ServerHttpRequest request = mock(ServerHttpRequest.class);
        ServerHttpResponse response = mock(ServerHttpResponse.class);
        WebSocketHandler handler = mock(WebSocketHandler.class);
        Map<String, Object> attributes = new HashMap<>();
        Principal trustedUser = () -> "alice";

        when(request.getPrincipal()).thenReturn(trustedUser);

        boolean proceed = interceptor.beforeHandshake(
                request, response, handler, attributes);

        assertTrue(proceed);
        assertEquals("alice", attributes.get(
                VerifiedUserHandshakeInterceptor.USER_ID));
        verify(response, never()).setStatusCode(HttpStatus.UNAUTHORIZED);
    }
}
```

Run in a Gradle project with the wrapper and dependencies listed above:

```bash
./gradlew test --tests '*VerifiedUserHandshakeInterceptorTest'
```

On Windows PowerShell, use `.\gradlew.bat test --tests '*VerifiedUserHandshakeInterceptorTest'`. When both cases pass, JUnit reports **2 tests passed** in the test report; there is no fixed stdout because this test does not call `System.out.println`.

This test verifies **the interceptor's behavior** before the handshake. It does not test full HTTP security, endpoint Origin policy, WebSocket upgrade, cookies, or STOMP authorization. Those require integration tests at their respective layers.

### 8.1 Integration testing Origin and security

Set up a test server with the configured `/ws` endpoint and an authenticated identity. Test these cases:

| Case | Expectation |
| --- | --- |
| Origin in allowlist and valid HTTP Principal | Handshake can proceed (if other protocol/security conditions are met) |
| Origin not in allowlist | Handshake rejected per Origin policy |
| No valid HTTP Principal | Rejected by HTTP security or interceptor; e.g., interceptor returns 401 if reached |
| Valid Origin but STOMP CONNECT lacks CSRF token when security requires it | WebSocket may upgrade, but CONNECT is blocked at the messaging layer |
| Authenticated user sends SEND to an unauthorized destination | Message rejected at authorization layer |
| Browser opens another tab / additional connection | Separate WebSocket sessions with separate metadata |
| STOMP CONNECT supplies a spoofed username | Must not overwrite the HTTP-authenticated Principal |

When testing handshakes with CLI tools, the `Origin` header can be crafted by the tool itself. A passing Origin check **does not prove the user is authenticated**. Real browser tests (cookies and CORS/Origin) and HTTP tool tests should be treated as complementary evidence.

Do not hardcode one exact status code for every Origin-rejection case: the final status can depend on whether Spring, Security, the container, or the handler rejects first. Tests should verify the request is rejected at the proper layer and for the expected reason, unless the application explicitly defines the status as part of a contract.

## 9. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Believing HTTP 101 means all STOMP destinations are permitted | Bypasses send or subscribe authorization | Configure Spring Security message authorization or an appropriate `ChannelInterceptor` |
| Allowing Origin `*` to "fix CORS errors" | Lets any website attempt WebSocket connections; cookie/session risk | Declare an exact Origin allowlist, accounting for scheme/host/port |
| Treating Origin as client identity | Non-browser clients can spoof Origin | Combine authentication, authorization, rate limits, and security policies |
| Taking `userId` from query string and storing in attributes | Users can claim any identity | Obtain a trusted `Principal` from HTTP Security or a verified token |
| Using `attributes.put(...)` expecting it to replace Principal | Metadata does not establish authentication | Use proper `Principal`/ChannelInterceptor mechanisms at the right layer |
| Trying to read STOMP CONNECT token in HandshakeInterceptor | CONNECT frame arrives after the handshake | Use a `ChannelInterceptor` on `clientInboundChannel` |
| Trusting default STOMP `login`/`passcode` | Spring generally ignores them when WebSocket auth relies on HTTP | Implement explicit authentication |
| Not checking permissions on every `SEND`/`SUBSCRIBE` | Authenticated users can access other users' data | Enforce authorization per user + destination |
| Putting raw JWTs or cookies into session attributes/logs | Exposes secrets and retains them long-term in sessions | Store minimal metadata and never log secrets |
| Using `setAllowedOrigins("http://localhost")` when frontend runs on a port | Cross-origin handshake fails | Configure the frontend's full scheme/host/port |
| Disabling CSRF globally just to let SockJS run | Opens vulnerabilities on other HTTP endpoints | Configure narrow exceptions and protect STOMP CONNECT properly |
| Basing Origin checks on untrusted forwarded headers | Policy bypass or false rejections | Trust forwarding headers only from controlled reverse proxies |

## 10. Summary and Self-Check Questions

**Decision chain to remember:**

```text
HTTP Security auth → Origin policy → HandshakeInterceptor
                  ↓ if accepted
        WebSocket session / Principal / attributes
                  ↓
        STOMP CONNECT (may include CSRF/token checks)
                  ↓
        STOMP SEND/SUBSCRIBE → message authorization → business logic
```

Self-review questions:

1. What does returning `false` from `HandshakeInterceptor.beforeHandshake` mean? **Stop the handshake before the WebSocket connection is opened.**
2. Why is `attributes.put("userId", "...")` not equivalent to authentication? **It only sets metadata; it does not prove identity or create a Principal.**
3. Where does `Origin` come from, and can it be trusted unconditionally? **Sent by browsers when initiating a WebSocket; non-browser clients can spoof it.**
4. How do you restrict which frontends can connect? **Use `setAllowedOrigins`/`setAllowedOriginPatterns` scoped as needed, alongside proper authentication.**
5. Why can't a STOMP CONNECT token be read inside an HTTP `HandshakeInterceptor`? **The handshake happens before the STOMP CONNECT frame.**
6. Is blocking unknown users at the handshake enough? **No; authenticated users still need authorization per destination and message type.**
7. Can a user open multiple WebSockets? **Yes; each connection has its own session ID and attributes, even when sharing the same Principal.**
8. Is the HTTP handshake state the state of every subsequent message? **No; the handshake only creates the session, while STOMP processing is a separate stage.**

In real applications, prioritize layered defenses: valid HTTP authentication, a trusted origin allowlist, minimal session info in interceptors, CONNECT protection where required, and message-level authorization.

## 11. Official Documentation

- [Spring Framework — WebSocket Server, Handshake, and Allowed Origins](https://docs.spring.io/spring-framework/reference/web/websocket/server.html).
- [Spring Framework — STOMP Enable Endpoints](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html).
- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html).
- [Spring Framework — Token Authentication on STOMP CONNECT](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html).
- [Spring Framework — STOMP Interception/Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html).
- [Spring Security — WebSocket Security, Same-Origin, CSRF](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html).
- [Javadoc — HandshakeInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/server/HandshakeInterceptor.html).
