# Origin, CSRF in STOMP CONNECT, and Their Relationship to Access Control

> Scope: Spring Security on the Servlet stack, Spring WebSocket Messaging with STOMP over WebSocket (optionally with SockJS). The focus is protecting the connection point and **authorizing every incoming message from clients**. Raw WebSockets without STOMP, RSocket, and WebFlux have different integration mechanisms.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish `Origin` validation at the WebSocket handshake, CSRF validation in STOMP `CONNECT`, and permission control on `SEND`/`SUBSCRIBE`.
- Explain why an attacker can exploit a logged-in browser to open a WebSocket against the user's intent (Cross-Site WebSocket Hijacking, CSWSH).
- Configure WebSocket protection with `@EnableWebSocketSecurity` and `AuthorizationManager<Message<?>>`, while passing the CSRF token via STOMP headers.
- Build a policy based on **message type + destination + user identity/permissions**, and test denied cases.

## 2. Three Distinct Layers of Control

| Stage | Key Data | Enforcement Mechanism | Question Answered |
| --- | --- | --- | --- |
| HTTP handshake, e.g., `GET /ws` with `Upgrade: websocket` | Cookies/HTTP credentials, `Origin`, URL | HTTP authentication, allowed-origin check configured in Spring WebSocket | May a browser from this origin open the transport? Can the user be identified? |
| STOMP `CONNECT` traveling **inside** the transport | STOMP headers, including CSRF token | Spring Security verifies the token for `CONNECT`; message authorization may require `authenticated()` | Is the STOMP session established by a legitimate request? |
| STOMP `SEND` (Simp `MESSAGE`), `SUBSCRIBE`, and subsequent frames | `simpUser`, message type, `destination` | `AuthorizationManager<Message<?>>` on `clientInboundChannel` plus business checks | Is this user allowed to send/subscribe to this destination? |

**No layer fully replaces another.** A valid handshake does not grant all permissions for every message. A valid CSRF token proves access to the token in a protected context, **not** permission to read secret topics or perform admin actions. An authenticated user still needs authorization per action.

Typical flow:

~~~text
Logged-in browser
  │
  ├─ 1. HTTP GET /ws + Cookie + Origin
  │       ├─ HTTP authentication / session
  │       └─ WebSocket allowed-origin check
  │                ↓
  ├─ 2. STOMP CONNECT + CSRF token in STOMP header
  │       ├─ Spring Security CSRF check
  │       └─ CONNECT permission check per message policy
  │                ↓
  ├─ 3. STOMP SUBSCRIBE /topic/updates
  │       └─ Policy: who may follow the topic?
  │                ↓
  └─ 4. STOMP SEND /app/chat.send
          ├─ Policy: who may send to the destination?
          └─ Handler: check permission on the specific chat room/object
~~~

## 3. Origin: Blocking Unauthorized Browser Origins

`Origin` identifies the origin of the page making the request (scheme + host + port), such as `https://app.example.com`. Unlike many `fetch`/XHR requests, **browsers do not automatically enforce the Same-Origin Policy to forbid JavaScript from opening a WebSocket to a different origin**. If the server does not check, a malicious page can open a WebSocket to an app where the user is logged in; when the browser attaches session cookies per active cookie policies, the server may treat the connection as carrying the victim's identity.

Spring Framework WebSocket/SockJS restricts to **same-origin** by default. Example:

~~~java
// WsTransportConfig.java - part of the Spring Boot application
package example.chat;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WsTransportConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws"); // Keep same-origin default.
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

This is the **handshake endpoint** `/ws`; it is not a STOMP destination like `/app/chat.send` or `/topic/updates`. When the frontend runs on a different trusted origin from the backend, declare an exact list, such as `registry.addEndpoint("/ws").setAllowedOrigins("https://app.example.com")`. Keep the list minimal, use HTTPS/WSS, and manage cookies/CORS properly. Never use `*` just to silence connection errors.

Limits of `Origin`:

- Standard browsers set `Origin` automatically, making it a critical signal to block unfamiliar web pages. **Non-browser clients can forge `Origin`**; hence it is not identity authentication.
- Allowed origins do not check STOMP payloads, roles, tenants, or resource permissions.
- REST API CORS and WebSocket allowed-origin are separate configurations; enabling CORS does not grant WebSocket access. With SockJS HTTP fallbacks, corresponding CORS/transport behavior must also be checked.
- `SameSite` cookies are a helpful layer, yet should not be the sole defense; cookie transmission also depends on context, browser, and implementation.

**Attack scenario:** the victim logs into `chat.example.com`, then visits `evil.example.net`. The malicious page runs `new WebSocket("wss://chat.example.com/ws")`. The server must reject the foreign origin; even if that origin were accidentally allowed, the CSRF layer at `CONNECT` must still stop a page lacking a valid token from establishing a STOMP session.

## 4. CSRF on STOMP CONNECT: Purpose and Delivery

CSRF (Cross-Site Request Forgery) arises when the browser automatically attaches credentials like cookies to an attacker-initiated request. Spring Security WebSocket Messaging requires a **valid CSRF token in STOMP `CONNECT`** by default when using `@EnableWebSocketSecurity`. This enforces deeper same-origin protection at the STOMP layer.

Distinguish two requirements:

1. `GET /ws` is the HTTP handshake; HTTP security rules apply. `Origin` checking occurs at the WebSocket layer. HTTP CSRF typically guards state-changing methods (like POST), so **do not assume HTTP CSRF checks at the GET handshake already protect STOMP CONNECT**.
2. After upgrading the transport, the client sends the STOMP `CONNECT` frame. The token must reside in a **native STOMP header**, not solely in an HTTP handshake header. Browser JavaScript or SockJS clients generally cannot set arbitrary HTTP headers on handshake/transport requests, whereas they can set STOMP `connectHeaders`.

Example frame (header name depends on server token configuration):

~~~text
CONNECT
accept-version:1.2
host:chat.example.com
X-CSRF-TOKEN:<valid-token>

^@
~~~

In the STOMP wire format, a frame ends with a **NUL byte (0x00)**; the `^@` notation above is illustrative only. Never hardcode `<valid-token>`.

One way to supply the token to a same-origin UI is the following controller. The endpoint should be accessible only within a valid session/context; browsers must not be able to read this response from a malicious origin:

~~~java
// CsrfEndpoint.java
package example.chat;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfEndpoint {
    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken token) {
        return token;
    }
}
~~~

Client using `@stomp/stompjs` (illustrative for a same-origin page):

~~~javascript
import { Client } from "@stomp/stompjs";

const response = await fetch("/csrf", { credentials: "same-origin" });
if (!response.ok) {
  throw new Error("Failed to fetch CSRF token: " + response.status);
}
const csrf = await response.json();

const client = new Client({
  brokerURL:
    (location.protocol === "https:" ? "wss://" : "ws://") +
    location.host + "/ws",
  connectHeaders: { [csrf.headerName]: csrf.token },
  onConnect: () => {
    client.subscribe("/topic/updates", (message) => {
      console.log(message.body);
    });
  },
  onStompError: (frame) => {
    console.error("STOMP rejected:", frame.headers.message);
  }
});

client.activate();
~~~

The JSON properties `headerName` and `token` come from `CsrfToken`; do not guess the header name, as configuration can vary. For cross-origin UIs, design token fetching, credentials, and CORS carefully with an exact allowlist; never allow untrusted origins to read `/csrf` with the victim's credentials. **Never put CSRF tokens into URL/query strings or logs.** Tokens can change after login/logout or session expiration; the client must re-fetch them when appropriate.

**Relationship to authorization:** A `CONNECT` with a valid CSRF token can still be rejected if the policy requires a logged-in user. Conversely, a `CONNECT.permitAll()` or `authenticated()` message authorization rule **does not disable the CSRF check** installed by `@EnableWebSocketSecurity`.

## 5. Authorizing Inbound MESSAGE and SUBSCRIBE After CONNECT

Spring Security checks messages arriving from clients on `clientInboundChannel`. Do not infer that it filters every outbound message on `clientOutboundChannel`: normally you must control **SUBSCRIBE permissions** to limit where users receive data, combined with handler-level and publisher-side authorization.

Sample scenario:

| Frame from client | Destination | Example Policy | Reason |
| --- | --- | --- | --- |
| `CONNECT` | No destination | Authenticated + valid CSRF | Binds STOMP session to a valid user |
| `SUBSCRIBE` | `/topic/updates` | Authenticated | Read-only internal general updates |
| `SUBSCRIBE` | `/user/queue/alerts` | Authenticated | Receive queue for the current user |
| `SEND` (Simp `MESSAGE`) | `/app/chat.send` | Authenticated; handler checks chat room permission | Send request into the application |
| `SEND` | `/topic/updates` | Deny | Clients must not spoof server/broker broadcasts |
| `SUBSCRIBE` | `/queue/**` or unapproved topics | Deny | Disallow reading raw queues or out-of-policy topics |

Implementation with Spring Security `AuthorizationManager` (suitable for Spring Security 6.x/7.x). Each class below goes in a matching file; pair with `WsTransportConfig` introduced earlier:

~~~java
// WsMessageAuthorizationConfig.java
package example.chat;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class WsMessageAuthorizationConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .simpTypeMatchers(
                SimpMessageType.CONNECT,
                SimpMessageType.DISCONNECT,
                SimpMessageType.UNSUBSCRIBE
            ).authenticated()
            .simpSubscribeDestMatchers("/topic/updates").authenticated()
            .simpSubscribeDestMatchers("/user/queue/alerts").authenticated()
            .simpMessageDestMatchers("/app/chat.send").authenticated()
            .simpTypeMatchers(
                SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE
            ).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

Exact explanation:

- `simpTypeMatchers` matches by message type; `simpMessageDestMatchers` matches only Simp `MESSAGE`, whereas `simpSubscribeDestMatchers` matches only `SUBSCRIBE`. **Do not use type-unrestricted `simpDestMatchers` when send and subscribe policies must differ.**
- Rules are evaluated in order; place permitted exceptions **before** `denyAll`. `/app` routes messages to `@MessageMapping`, while `/topic`/`/queue` are broker destinations in the example.
- `authenticated()` on `CONNECT` relies on the `Principal` bound to the WebSocket session from HTTP authentication in the standard model. If allowing anonymous connections to read public data, explicitly redesign both policy and CSRF.
- `/user/queue/alerts` is a client-side user destination; the server maps it to a session-specific destination. Never open `SUBSCRIBE` directly on `/queue/**`.
- The final `denyAll` ensures unreviewed messages/destinations are never permitted automatically. If the app needs heartbeats, receipts, or other frame types, add intentional policies and test them.

For HTTP flows using session login, the application also needs a matching `SecurityFilterChain`: authenticating pages/HTTP endpoints, protecting `/csrf` and `/ws`, and keeping HTTP CSRF for state-changing operations. Having a message authorization bean **does not create an HTTP login mechanism**. In the standard session/cookie model, Spring WebSocket propagates the `Principal` from the handshake request to STOMP messages; STOMP `login`/`passcode` headers are not automatically used by Spring to log users in.

The Java examples above require a corresponding Spring Boot project (Java 17+, Spring WebSocket Messaging, Spring Security web, and `spring-security-messaging` dependencies); these are configuration classes inside an application, **not standalone Java programs runnable with `javac` without dependencies**. Do not fabricate stdout from these configurations; effectiveness is verified through real connections and allow/deny decisions.

### Why Must the Handler Still Check Business Permissions?

The rule for `/app/chat.send` shows only that the user is logged in and allowed to call that destination. The payload may carry `roomId=42`; the handler must verify the user is actually a member of room 42, check tenant bounds, operation type, and validate input data. Never trust client-sent `senderId`, `role`, or `tenantId` in place of the verified `Principal`.

Conceptual handler logic example:

~~~text
SEND /app/chat.send  {roomId: 42, text: "Hello"}
  → authenticate user from session Principal
  → check room 42 membership on server
  → reject if not a member
  → save/send message if valid
~~~

The sketch above describes business logic only; it is not standalone Java source. For per-resource topics such as `/topic/rooms/42`, even `SUBSCRIBE` permission must verify access to room 42 rather than using `authenticated()` alone.

## 6. SockJS: Distinguishing HTTP CSRF from STOMP CSRF

SockJS can fall back to transport over HTTP POST. Those POSTs pass through the HTTP `CsrfFilter`, while SockJS JavaScript cannot easily attach a token via HTTP headers on every fallback request. If the application **actually enables** `withSockJS()` and needs fallback, Spring Security docs advise ignoring **HTTP CSRF on the exact SockJS transport URLs**, while still keeping CSRF checks in STOMP `CONNECT`. These are two separate layers.

Optional example for a `/ws` endpoint using SockJS, inside the app's HTTP configuration:

~~~java
// Configuration snippet inside SecurityFilterChain (optional with SockJS).
http.csrf(csrf -> csrf.ignoringRequestMatchers("/ws/**"));
~~~

- This snippet **does not need to be applied by default** for pure WebSockets without SockJS fallback needs.
- Ignore HTTP CSRF only for the exact transport path (here `/ws/**`); never call `csrf.disable()` site-wide.
- STOMP `CONNECT` still requires the token in STOMP headers and is still verified by Spring Security. If the same endpoint also serves state-changing HTTP APIs, separate the paths and re-audit the ignore scope.
- Some fallbacks use iframes; if the app needs them, `X-Frame-Options: SAMEORIGIN` instead of DENY may be needed with an appropriate safety scope. Do not relax framing unnecessarily.

Do not disable WebSocket CSRF just to make connections succeed. If an architecture truly avoids cookies and authenticates with a bearer token sent explicitly in STOMP `CONNECT`, re-evaluate the threat model, how the `Principal` is set before the security interceptor, and version compatibility. When using a custom token interceptor, Spring Framework notes you must ensure the authentication interceptor runs **before** Spring Security message authorization. Do not treat the cookie/session config in this lesson as a complete JWT example.

## 7. Cases That Should and Should Not Be Allowed

Suppose user Alice is logged in, the origin is valid, and the client obtains a fresh CSRF token:

1. **Valid origin + valid session + right token + `CONNECT`**: passes checks and proceeds to message rules.
2. **Foreign origin**: handshake is rejected even though the browser may attach cookies; do not wait until SUBSCRIBE to block.
3. **Allowed origin, yet `CONNECT` missing/wrong token**: the WebSocket transport may open, yet the STOMP session fails CSRF validation and cannot operate.
4. **Valid token, yet anonymous under a login-required policy**: `CONNECT` is rejected by authorization.
5. **Alice SUBSCRIBEs to `/topic/updates`**: permitted by policy; the server emits only data appropriate for that audience.
6. **Alice SENDs to `/topic/updates`**: blocked by `denyAll`; server-emitted notifications must originate from trusted paths.
7. **Alice SUBSCRIBEs to `/topic/rooms/42`**: the policy above does not open this destination so it is denied; opening it requires adding room 42 membership checks.
8. **Alice SENDs to `/app/chat.send` without room 42 access**: the message-level rule may pass to the handler, and **the handler must reject** the business operation.

Depending on handshake, STOMP client, and library version, failures may manifest as HTTP rejections, STOMP `ERROR` frames, closed connections, or exceptions in logs. **Do not assume an exact HTTP status code for every case**; verify on the running system.

## 8. Deployment Testing Checklist

| Scenario | How to Test | Expected Result |
| --- | --- | --- |
| Same-origin | Open connection from frontend on valid origin | Handshake evaluated per HTTP auth; `CONNECT` still requires token |
| Unauthorized cross-origin | Page from another origin invokes WebSocket | Handshake rejected per allowlist |
| Missing CSRF | Client connects omitting token in `connectHeaders` | `CONNECT` fails |
| Wrong/expired token | Send token not matching session | `CONNECT` fails |
| Anonymous | No logged-in session | `CONNECT.authenticated()` rule rejects |
| Valid topic | Authenticated client SUBSCRIBEs `/topic/updates` | Allowed |
| Send to broker | Authenticated client SENDs `/topic/updates` | Rejected |
| Out-of-policy subscribe | SUBSCRIBE `/queue/someone-else` | Rejected |
| Business privilege violation | SEND to a chat room the user does not belong to | Handler rejects even though message matched |
| SockJS fallback (if enabled) | Run HTTP fallback and send STOMP CONNECT token | HTTP transport works; STOMP CSRF still enforced |

Also test session logout/expiration, reconnect after token rotation, split-origin frontend setups, and client-crafted destinations. In automated tests, assert **both the handshake and the frames**; testing only HTTP `GET /ws` is insufficient. When inspecting logs, never print CSRF tokens, cookies, or bearer tokens.

## 9. Common Mistakes

- **Confusing `Origin` with authentication:** this header can be spoofed outside browsers and does not answer "who is the user?".
- **Confusing CORS with WebSocket protection:** configure allowed origins for WebSocket/SockJS in the right place.
- **Treating handshake success as blanket authorization:** HTTP 101 or `CONNECTED` does not grant SEND/SUBSCRIBE to every destination.
- **Checking CSRF only on HTTP:** Spring Security also guards STOMP `CONNECT`; send the token in `connectHeaders`, not just HTTP headers.
- **Disabling all CSRF to fix SockJS:** scope any HTTP exception strictly to the transport path and retain the STOMP CSRF layer.
- **Allowing clients to SEND directly to broker prefixes:** users can spoof system announcements if the policy fails to block it.
- **Opening `/queue/**` or `/topic/**` broadly:** can leak other users' data; prefer SUBSCRIBE allowlists and per-resource authorization.
- **Trusting identity/roles inside payloads:** obtain the `Principal` from the security context and verify real permissions server-side.
- **Using legacy config APIs:** `AbstractSecurityWebSocketMessageBrokerConfigurer` belongs to the old approach and was removed in Spring Security 7; examples here use `AuthorizationManager<Message<?>>`.

## 10. Takeaways and Official Documentation

Remember three questions in order: **(1) Is the browser's Origin allowed to open the transport? (2) Does STOMP CONNECT carry a valid CSRF token and a valid user? (3) Is the user allowed to perform this message type/destination/resource action?** Each step controls a distinct risk, combining to prevent CSWSH, message spoofing, and unauthorized reads of broker data.

References from the Spring project (check against your application's dependency versions):

- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- Spring Framework — WebSocket allowed origins: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
- Spring Framework — STOMP authentication: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html
- Spring Framework — STOMP token authentication: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html
- Spring Framework — STOMP authorization: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html
