# Authentication, Origin, and Session Info During the WebSocket Handshake

In **Spring Cloud Gateway**, ordinary REST requests end after a single HTTP response. With **WebSocket**, the client first sends an HTTP **handshake** request, after which the connection upgrades into a bidirectional channel that can live for minutes or hours. Therefore, checking identity, **Origin**, and **session info** at handshake time is just as critical as forwarding `ws://` or `wss://` accurately to the microservice.

A WebSocket that connects yet **authenticates the wrong user**, **accepts an unknown Origin**, or **mixes up sessions across tenants** can leak chat events, notifications, or live data without authorization. Conversely, the system can return `401`, `403`, `404`, or `502` during the handshake even while the backend and standard HTTP routes still work.

This lesson belongs to the **WebSocket and Streaming** chapter and focuses on how Spring Cloud Gateway Server WebFlux receives handshakes, coordinates with **Spring Security**, validates `Origin`, forwards cookies/tokens, and manages session state. Concepts connect back to route predicates, the Gateway filter chain, service discovery via `lb://`, TLS, rate limiting, circuit breakers, retries, and request observability to operate a secure microservices ingress.

> **Scope:** Examples use **Spring Cloud Gateway Server WebFlux** with the standard WebSocket-over-HTTP/1.1 Upgrade mechanism. HTTP/2 extended CONNECT uses a separate handshake mechanism and requires checking each proxy/server's capabilities; do not assume Upgrade examples apply verbatim to it. Starter names, configuration properties, and Security/WebSocket proxy behaviors may vary across Spring Boot/Spring Cloud Gateway versions. **Origin does not replace authentication**, and a valid WebSocket handshake does not automatically prove every subsequent message is authorized.

## 1. WebSocket Starts with an HTTP Request

In a browser, application code can open:

```javascript
const socket = new WebSocket(
  "wss://api.example.test/ws/chat/rooms/42",
  ["chat.v1"]
);

socket.onopen = () => console.log("WebSocket connected");
socket.onmessage = event => console.log(event.data);
socket.onclose = event =>
  console.log("Closed:", event.code, event.reason);
socket.onerror = () => console.log("Connection error");
```

When using HTTP/1.1 Upgrade, the browser sends roughly:

```http
GET /ws/chat/rooms/42 HTTP/1.1
Host: api.example.test
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <random-base64-key>
Sec-WebSocket-Version: 13
Sec-WebSocket-Protocol: chat.v1
Origin: https://app.example.test
Cookie: SESSION=<browser-session-id>
```

Each field has a distinct role:

| Component | Role | What to watch |
| --- | --- | --- |
| `GET /ws/...` | HTTP path of the handshake | Must match route predicate and upstream path |
| `Host` | Target host of Gateway | Can affect `Host` predicate and TLS/SNI |
| `Upgrade: websocket` | Requests protocol switch in HTTP/1.1 | Proxy must support Upgrade |
| `Connection: Upgrade` | Declares hop-by-hop Upgrade in HTTP/1.1 | Ingress must be configured to forward properly |
| `Sec-WebSocket-Key` | Nonce used to compute handshake accept | **Not an access token** |
| `Sec-WebSocket-Version: 13` | WebSocket protocol version | Not the application version |
| `Sec-WebSocket-Protocol` | Proposes subprotocols such as `chat.v1` | **Not by default a place to pass Bearer tokens** |
| `Origin` | Origin of the page initiating the connection per browser | Used to enforce browser origin policy; does not prove identity |
| `Cookie` | May hold Gateway/application session | Subject to browser cookie policy and host/path settings |

If every handshake condition passes, the HTTP/1.1 server can respond:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <derived-accept-value>
Sec-WebSocket-Protocol: chat.v1
```

After `101 Switching Protocols`, both sides exchange **WebSocket frames**, with no separate HTTP request/response per message. Gateway normally maintains a proxy connection to the backend WebSocket and relays frames both ways.

**Separate the two phases:** Before `101`, Gateway and Security can reject with HTTP statuses like `401`/`403`. After `101`, policy errors are conveyed with a **WebSocket close frame/close code**; you cannot replace an already upgraded connection with an HTTP `401`.

## 2. Where Does the WebSocket Handshake Sit in Gateway?

A typical logical path:

```mermaid
sequenceDiagram
    participant B as Browser
    participant I as Ingress / TLS terminator
    participant G as Spring Cloud Gateway WebFlux
    participant S as Spring Security / WebFilter
    participant L as LoadBalancer
    participant U as chat-service
    B->>I: GET /ws/chat + Upgrade + Origin + Cookie
    I->>G: Forward HTTP/1.1 handshake
    G->>S: Check authentication / origin policy
    alt Rejected before upgrade
        S-->>B: 401 / 403 / redirect per policy
    else Allowed
        G->>L: Route lb:ws://chat-service
        L->>U: WebSocket handshake to instance
        U-->>G: 101 if upstream accepts
        G-->>B: 101 Switching Protocols
        B<->>U: WebSocket frames through Gateway
    end
```

The diagram shows an **architectural model**, not the exact same hook/proxy class order across every version. Spring Security in the WebFilter chain normally runs before `RoutePredicateHandlerMapping`; once a route matches, Gateway filters and WebSocket routing proxy downstream.

### Boundaries to Separate

- **Security before route:** authenticates/authorizes the incoming handshake request.
- **Gateway route predicate:** selects the route by `Path`, `Host`, `Method`, headers...
- **Gateway filters:** can transform paths/headers or enforce handshake policies.
- **WebSocketRoutingFilter:** inspects the `ws`/`wss` scheme of the target URL to route the handshake and relay frames per Gateway's capabilities.
- **Upstream WebSocket server:** may enforce independent authentication, Origin, subprotocol, and message authorization.
- **Ingress:** can block or strip headers needed for HTTP Upgrade before the request even reaches Gateway.

A handshake error is not automatically a backend bug. For instance, if Security returns `401`, `WebSocketRoutingFilter` may **not have run yet**.

## 3. Route Config for `ws://`, `wss://`, and Service Discovery

Example WebSocket route when the backend is resolved via Spring Cloud LoadBalancer:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: chat-websocket
          uri: lb:ws://chat-service
          predicates:
            - Path=/ws/chat/**
          filters:
            - StripPrefix=1
```

Suppose the browser opens:

```text
wss://api.example.test/ws/chat/rooms/42
```

In this example:

1. Ingress or Gateway receives public `wss://`.
2. `Path=/ws/chat/**` selects the WebSocket route.
3. `StripPrefix=1` drops the `ws` segment, leaving `/chat/rooms/42` downstream.
4. `lb:ws://chat-service` resolves `chat-service` to an instance and uses the WebSocket scheme.
5. Once the proxied handshake succeeds, frames flow across the upgraded connection.

**Check the expected upstream path.** If `chat-service` expects `/ws/chat/rooms/42`, adding `StripPrefix=1` breaks the path. Test with a WebSocket client or backend access logs; an HTTP route returning `200` does not prove the WebSocket handshake works.

### Do Not Confuse `lb:ws://` with `lb://`

In Gateway versions supporting `lb:ws://service-id`, `lb` requests load balancing and `ws` specifies downstream WebSocket. For TLS-enabled backends, `lb:wss://chat-service` is typically used (subject to version support and actual backend TLS). Bare `lb://chat-service` can be interpreted as plain HTTP and **does not guarantee the WebSocket routing filter is chosen**.

Never substitute `https://` for `wss://` without checking Gateway's routing scheme. Public wss terminated at Ingress can still proxy internally over ws if **trust boundaries and policy permit**; environments requiring end-to-end encryption must use wss/mTLS between layers.

### Configuration Prefix Depends on Version

Newer Spring Cloud Gateway Server WebFlux releases use `spring.cloud.gateway.server.webflux.routes` instead of the traditional `spring.cloud.gateway.routes`. Verify the starter and configuration metadata of your running version. Valid YAML under the wrong prefix prevents routes from loading and causes handshakes to return `404`.

### The WebSocket Connection After Instance Selection

LoadBalancer normally selects an instance for the **handshake**, not again for every WebSocket frame. Once connected:

```text
Browser <---- persistent socket ----> Gateway <---- socket ----> chat-instance-B
```

If discovery updates its instance list, active connections **do not automatically jump** to another instance like a new HTTP request. When instance B stops, the client loses its socket and must **reconnect with fresh authentication/authorization**, using backoff/jitter and application state recovery.

## 4. Handshake Authentication: Proof of Identity Before `101`

For HTTP APIs, Spring Security verifies JWTs or sessions before calling the backend. Because a handshake is also an HTTP request, **it is the early opportunity to reject** unauthenticated clients.

Example requiring a logged-in user to open `/ws/**`:

```java
@Configuration
public class GatewayWebSocketSecurity {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/ws/**").authenticated()
                .anyExchange().permitAll())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
```

This snippet only **illustrates reactive Spring Security**; it needs imports, the OAuth2 Client dependency, login/client registrations, a session store, and policies for other APIs. **Never copy `anyExchange().permitAll()` into production** if the app has protected REST APIs, Actuator endpoints, or other routes. Always separate security matchers and enforce full authorization.

When a user lacks a session, OAuth2 login may return an **HTTP redirect to the login page**. The browser WebSocket API **is not an interactive login flow**; a handshake redirect manifests as a failed connection rather than transparently completing login like a web page.

**Safer BFF pattern:** the browser logs in first over HTTPS/OIDC; once a valid session cookie exists, it calls `new WebSocket(...)`. If the session expires, the app re-authenticates over HTTPS and reopens the socket.

### With Stateless Bearer Token APIs

Gateway can validate Bearer tokens via Resource Server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
```

```java
@Bean
SecurityWebFilterChain websocketApiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/ws/**").hasAuthority("SCOPE_chat.connect")
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

However, there is a major restriction: **the browser JavaScript WebSocket API does not allow adding an arbitrary `Authorization` header**. Therefore code like:

```javascript
// NOT valid browser WebSocket API:
new WebSocket("wss://api.example.test/ws/chat", {
  headers: { Authorization: "Bearer <token>" }
});
```

**does not work as expected**. The second argument of the `WebSocket` constructor is **subprotocol(s)**, not a headers config object. Non-browser clients can set headers using their own libraries, so verify against actual client types.

### Authentication Options for Browsers

| Option | How it works | Trade-offs |
| --- | --- | --- |
| **Session cookie / BFF** | Login via HTTPS; browser auto-sends valid cookie when opening `wss://` | Requires Origin policy, SameSite/CSRF, session storage, and revocation |
| **Short-lived one-time handshake ticket** | Client fetches a ticket over authenticated HTTPS; Gateway/upstream verifies it at handshake | Requires single-use, user/tenant binding, TTL, and log redaction |
| **Token in query string** | `wss://.../ws?ticket=...` | Can leak into proxy logs/traces/history; consider only short-lived tickets, never long-lived access tokens |
| **Credential inside `Sec-WebSocket-Protocol`** | Uses subprotocol as a token carrier | Breaks protocol semantics, leaks via logs and echoed response headers; never treat as standard |
| **Post-101 auth message** | Client sends initial auth message per application protocol | Socket is already upgraded; must block all messages pre-auth and manage timeouts/races |
| **Non-browser Authorization header** | CLI/mobile/native client sets `Authorization: Bearer ...` on handshake | Works where client libraries allow headers; does not mean browsers support it |

**Security recommendation:** for browser apps using Gateway as a BFF, prefer **secure session cookies** paired with an Origin allowlist, then enforce permissions per **resource/message** as needed. Without sessions, design **short-lived, single-use tickets** over HTTPS; never send refresh tokens or long-lived access tokens in query URLs.

## 5. Origin in WebSocket: Completely Different from Standard HTTP CORS

A page at:

```text
https://app.example.test
```

opens:

```text
wss://api.example.test/ws/chat
```

The browser typically sends:

```http
Origin: https://app.example.test
```

`Origin` describes the **source of the page opening the WebSocket**, normally **scheme + host + port**. It is not the WebSocket URI, contains no path/query, and carries no user ID or tenant ID.

### Comparing the Two Mechanisms

| Factor | Cross-origin Fetch/XHR | Browser WebSocket handshake |
| --- | --- | --- |
| Sends `Origin`? | Usually sent when CORS checks apply | Browser normally sends it |
| HTTP `OPTIONS` preflight? | Sent in certain scenarios | **Does not use standard CORS preflight** |
| Browser checks `Access-Control-Allow-Origin`? | Yes per CORS response semantics | **Does not apply Fetch-style CORS checks like XHR** |
| Server must verify Origin? | CORS layer enforces origin policy | **Must check Origin per WebSocket security policy** |
| Cookies/credentials? | Controlled by `fetch(credentials)` and cookie policy | Controlled by browser cookie policy on handshake; `WebSocket` constructor has no `credentials` option |
| Can unknown websites try opening? | Subject to CORS and server | Browser can **attempt** to open; server must reject disallowed Origins |

**Key takeaway:** `Access-Control-Allow-Origin` configured for REST **does not protect WebSocket automatically**. Enabling Gateway's `globalcors` for `/ws/**` is not proof that WebSocket Origin checks are enforced properly either.

### Cross-Site WebSocket Hijacking (CSWSH)

If a user logs in to `api.example.test` with a session cookie and visits `https://evil.example.test`, the malicious page can try:

```javascript
// Example attack behavior that must be blocked on the server, not recommended app code.
const ws = new WebSocket("wss://api.example.test/ws/private");
ws.onmessage = event => {
  // Untrusted page tries to read data if the server accepts the connection.
  console.log(event.data);
};
```

If the browser sends the session cookie and the server checks only the cookie **without validating Origin**, the malicious site can piggyback on the user's session to open a socket and read frames. This risk is **Cross-Site WebSocket Hijacking**.

`SameSite` cookies are an important mitigation, yet **must not replace Origin validation**. "Same-site" differs from "same-origin"; subdomains or browser policies can still allow cookies to be sent. Moreover, third-party cookie behaviors shift across browsers.

### Origin Allowlist Is Not Authentication

The `Origin` header can be **spoofed by non-browser clients** or omitted entirely. Therefore:

1. Check `Origin` to prevent untrusted browser pages from abusing a user's cookies/session.
2. **Simultaneously** authenticate the user/token/ticket.
3. Verify the user is authorized for the target channel/resource/tenant.
4. Define explicit policies for clients **lacking Origin**; never assume missing Origin is safe if an API is browser-only.
5. Never treat `Origin: https://app.example.test` as proof that the user owns an account in that app.

## 6. Checking Origin Early in Gateway

When Gateway proxies WebSockets to a backend, one design checks Origin in a **`WebFilter`** before route/WebSocket handshake upgrade. Pick an explicit origin allowlist:

```text
Allowed:
  https://app.example.test
  https://admin.example.test

Disallowed:
  http://app.example.test
  https://evil.example.test
  https://app.example.test.evil.example
  Empty Origin (in the browser-only example policy)
```

Never use `endsWith("example.test")` without delimiter/IDN checks, as `evil-example.test` slips past. If wildcard subdomains are necessary, parse the origin URL cleanly, verify scheme/port, and permit only hostnames you actually control; limit wildcards proactively.

### Illustrative WebFlux Code

```java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public final class WebSocketOriginGuard implements WebFilter {

    private static final Set<String> ALLOWED_ORIGINS = Set.of(
        "https://app.example.test",
        "https://admin.example.test"
    );

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        ServerHttpRequest request = exchange.getRequest();

        boolean wsPath = request.getPath().value().startsWith("/ws/");
        boolean upgrade = "websocket".equalsIgnoreCase(
            request.getHeaders().getUpgrade());
        boolean handshake = wsPath
            && request.getMethod() == HttpMethod.GET
            && upgrade;

        if (!handshake) {
            return chain.filter(exchange);
        }

        String origin = request.getHeaders().getOrigin();
        if (origin == null || !ALLOWED_ORIGINS.contains(origin)) {
            exchange.getResponse()
                .setStatusCode(HttpStatus.FORBIDDEN);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}
```

This is an **academic sample for HTTP/1.1 Upgrade**: add imports, review filter ordering, path matching, proxy deployment, and error handling. Systems supporting **HTTP/2 extended CONNECT** need matching detection/checks for H2 WebSockets or infrastructure constrained strictly to H1 Upgrade; a guard inspecting only `Upgrade` can **miss** the H2 path. If the Spring WebSocket handler/backend enforces its own Origin policy, keep all layers consistent instead of relying ambiguously on any single layer.

**Ordering note:** a `WebFilter` can run before Gateway route matching, rejecting unknown Origins as soon as requests arrive. However, the filter above **performs no authentication**. The downstream Security chain must still verify principals/permissions.

### Do Not Equate Origin with All Subdomains

Suppose the app runs at `https://app.example.test`. Do not configure a broad wildcard:

```text
https://*.example.test
```

if any subdomain lets customers host custom HTML/JS or is controlled by third parties. A malicious site sharing the parent domain may count as same-site under some cookie rules, so Origin allowlists must reflect **actual administrative control over each host**.

## 7. Cookies, HTTP Sessions, and `WebSocketSession`

Three concepts are often conflated:

| Concept | Role | Lifecycle |
| --- | --- | --- |
| **Session cookie** | Browser sends a session identifier in HTTP handshake when cookie policy permits | Depends on cookie expiry, logout, and browser |
| **WebFlux `WebSession`** | Server-side HTTP session state, usable with OAuth2 login/BFF | Depends on session store/TTL and storage mechanism |
| **`WebSocketSession`** | Abstraction of **one upgraded WebSocket connection** | From 101 success until close/disconnect |

**`WebSocketSession` ID is not an HTTP session ID.** One user can open multiple browser tabs, each with its own WebSocket connection sharing the same session cookie. One Gateway/backend can hold many `WebSocketSession` instances bound to the same principal.

### Are Cookies Always Sent?

No. Browsers decide cookie eligibility based on at least:

- Does the cookie `Domain` match the target host?
- Does `Path` match the handshake URL?
- Does `Secure` align with `wss://`/HTTPS per browser policy?
- `SameSite` and site relationship between page and target?
- Browser third-party cookie / tracking-prevention rules?
- Is the cookie unexpired, un-logged-out, and undeleted?

When debugging "REST login works yet WebSocket returns 401," never assume Gateway received the cookie. Inspect **handshake request headers** in DevTools and the session store in test environments. Avoid pasting real session cookie values into screenshots or issues.

### Session-Based BFF Pattern

A clean flow:

```mermaid
sequenceDiagram
    participant B as Browser
    participant G as Gateway BFF
    participant I as Identity Provider
    participant U as chat-service
    B->>G: HTTPS login
    G<->>I: OIDC authorization-code flow
    G-->>B: Set-Cookie: SESSION (Secure, HttpOnly, SameSite...)
    B->>G: WSS handshake + Origin + Cookie
    G->>G: Verify Origin + session + route authorization
    G->>U: Proxied WebSocket handshake
    U-->>G: 101 if accepted
    G-->>B: 101, connection opened
```

A session cookie is a credential for Gateway to **look up a session**; it is not a JWT access token the backend validates directly. If the backend needs user identity, design trustworthy propagation: e.g., an audience-scoped token verified by the backend, or a signed identity assertion within a trusted network.

**Do not assume HTTP REST `TokenRelay` automatically propagates OAuth2 authorized clients/tokens in every WebSocket handshake.** Test actual Gateway filter ordering, WebSocket routing handshake headers, and backend validation. Token audience and scopes still must match downstream.

## 8. What Information Should Be Forwarded Upstream?

Gateway generally preserves WebSocket handshake fields like the URL and Upgrade/Subprotocol headers per its proxy mechanics. However, **never assume every header, cookie, principal, or token passes through intact** in every Gateway release. HTTP proxying and WebSocket proxying can invoke different filters/hooks.

### Field Classification

| Field | May appear in handshake | Design rule |
| --- | --- | --- |
| `Origin` | Sent by browser | Backend/Gateway enforce policy; never treat as identity |
| `Cookie` | When browser cookie policy permits | Forward only if upstream genuinely needs it and trust boundary allows |
| `Authorization` | Non-browser clients may send | Must verify; optionally swap for an audience-scoped token |
| `Sec-WebSocket-Protocol` | Proposed subprotocol list | Pick only supported subprotocols; never store secrets |
| `Host` | Public target of request | Proxy must handle host/trusted forwarded host properly |
| `X-Forwarded-For/Proto/Host` | Proxy metadata | Trust only from configured/approved ingress; never trust client-asserted values |
| `X-User-Id/X-Tenant-Id` | Custom identity headers | **Never trust client-writable values** |
| `Sec-WebSocket-Key` | Handshake protocol field | Never use as session/token |
| Query `ticket=...` | Application-designed ticket | Enforce TTL/single-use, redact logs, prevent replay |

### Never Forward Raw Cookies to Every Backend

If Gateway acts as a BFF and the session cookie authenticates only with Gateway, the chat backend may not need that cookie. Forwarding session IDs to downstream services widens credential exposure and couples systems together.

When the backend needs user identity, prefer:

- An internal token with exact audience/scopes issued by a trusted AS.
- A time-bounded signed assertion verified by the backend.
- A trusted service-to-service channel with dedicated authorization, **never** relying solely on `X-User-Id`.

Depending on architecture, the WebSocket backend can also validate the same session/cookie directly, provided you understand session stores/trust boundaries and avoid accidental Gateway cookie forwarding.

### Query Tokens Leak Easily

Pattern to avoid for long-lived access tokens:

```text
wss://api.example.test/ws/chat?access_token=<long-lived-token>
```

URLs get persisted in Ingress/Gateway access logs, APM traces, error reports, and debugging tools. If a URL ticket is unavoidable because browsers cannot set Authorization headers, use a **very short-lived, single-use ticket** bound to user/tenant/resource over TLS, with replay protection and query redaction at every tier.

**Never send refresh tokens** in handshake URLs, subprotocols, or WebSocket messages just to "keep sessions alive longer."

## 9. Gateway Authentication and Upstream Authorization Are Two Separate Tasks

A handshake can authenticate principal "Alice," yet Alice **lacks permission to enter room 42**. With URL:

```text
wss://api.example.test/ws/chat/rooms/42
```

if Gateway only checks `authenticated()`, any logged-in user can attempt opening someone else's room. Authorization is needed at three levels:

1. **Handshake-level:** Is the user allowed to connect to the WebSocket service and target resource/tenant?
2. **Message-level:** Is the user allowed to subscribe to channel X, send messages to room Y, or invoke command Z?
3. **Connection lifetime:** When permissions change, must open connections be restricted/closed/re-authenticated?

### Per-Resource Authn and Authz

| Check | Example | If missing |
| --- | --- | --- |
| Authentication | Verify cookie/session/JWT/ticket | Anonymous users connect to private endpoints |
| Origin allowlist | Allow only organization-controlled frontends | CSWSH via browser holding a session |
| Tenant membership | User genuinely belongs to route/room tenant | Cross-tenant data leak |
| Resource permission | User allowed in chat room 42 | Reading someone else's room |
| Topic/channel permission | User allowed to subscribe to `/topic/admin` | Message leak over STOMP/subprotocol |
| Message rate/size | Cap frame and message rates | Spam, memory pressure |
| Revocation | User locked or permissions changed | Old socket keeps receiving data |

**Gateway route `Path=/ws/chat/**` only selects a destination**, not resource authorization. The backend or a trusted authz service must verify permissions for the exact room/topic requested.

## 10. STOMP or Application Protocols Do Not Replace the Handshake

Some systems run **STOMP over WebSocket**, creating two layers:

```text
HTTP/1.1 WebSocket handshake
    GET /ws/chat
    Origin, Cookie, Upgrade, ...
    -> 101 Switching Protocols

STOMP frames (after 101)
    CONNECT
    SUBSCRIBE destination:/topic/rooms/42
    SEND destination:/app/chat/42
    ...
```

An `Authorization` header inside a **STOMP CONNECT frame** (if used by the app protocol) **is not the HTTP Authorization header at handshake**.

Consequences:

- Gateway's Security WebFilter can block the HTTP handshake before `101`.
- If the server allows anonymous handshakes and authenticates only on STOMP CONNECT, a socket is already allocated before app credentials are checked.
- Block SUBSCRIBE/SEND until authentication completes.
- Enforce permissions **per destination/resource**, not only once on CONNECT.
- A standard Gateway WebSocket proxy **does not parse or authorize individual STOMP frames**. The backend messaging layer typically owns that responsibility.

Never assume HTTP Spring Security OAuth2 Resource Server automatically protects every message broker destination. Messaging security must be tested independently.

### WebSocket Messages Have No Origin Header

`Origin` belongs only to the **HTTP handshake request**. After `101`, WebSocket frames carry no HTTP headers like Origin or Cookie per message. The backend may cache the principal in session context and must validate permissions for each critical message.

If a user's permissions are revoked mid-session, the initial handshake does not re-run automatically. Enforce a policy to **close the socket, downgrade access, refresh auth state, or revalidate on resource access**.

## 11. Session Expiry and Logout While Sockets Remain Open

Suppose a user logs in, keeps a WebSocket open for 30 minutes, and the HTTP session expires after 15 minutes. Several behaviors can arise:

| Event | What not to assume | Required policy |
| --- | --- | --- |
| Cookie/session expires | WebSocket closes automatically | Enforce session max age/connection lifetime and revalidation |
| Logout on another tab | All open sockets close automatically | Server-side close by principal/session and logout event handling |
| JWT expires | Frames stop flowing automatically | Connection expiry/re-auth protocol and message-level authorization |
| User locked | Gateway notifies every backend automatically | Revocation fan-out or permission rechecks |
| Tenant membership changes | Subscribed topics unsubscribe automatically | Revalidate permissions and unsubscribe/close |
| Gateway replica restarts | WebSockets migrate instances seamlessly | Reconnect, resume/replay events per protocol |
| Backend rolling deploy | Active connections rebalance automatically | Draining and reconnects with backoff |

**`WebSocketSession` outlives the HTTP request that created it.** Security requires a connection-wide strategy rather than stopping at `101`.

### Closing a Connection Does Not Recall Already Sent Data

If a user received sensitive messages before being locked, closing the socket afterward does not erase that data. Pre-delivery authorization and response/message isolation remain paramount.

### Reconnect Strategy

Clients should:

1. Distinguish normal closure from unexpected disconnects.
2. Use exponential backoff with jitter, bounding attempts and max delay.
3. Re-check session/login status before reconnecting on auth errors.
4. Avoid infinite retries when the server returns a policy violation.
5. Pass an **application-protocol** resume token/sequence number if missed messages need recovery, subject to permission checks.
6. Avoid resending messages with side effects without idempotency/ack semantics.

## 12. WebSocket Close Codes and Handshake HTTP Statuses

Separate the two phases:

| Phase | Signal | Example meaning |
| --- | --- | --- |
| Pre-upgrade | HTTP `101` | Handshake succeeded |
| Pre-upgrade | HTTP `401` | Missing or invalid credentials |
| Pre-upgrade | HTTP `403` | Disallowed Origin or missing authorization |
| Pre-upgrade | HTTP `404` | Missing route/handler or wrong path |
| Pre-upgrade | HTTP `426` | Server requires protocol upgrade per contract |
| Pre-upgrade | HTTP `502/503/504` | Gateway proxy failure / no instance / upstream timeout |
| Post-upgrade | Close code `1000` | Normal closure |
| Post-upgrade | Close code `1001` | Going away, e.g., server shutting down |
| Post-upgrade | Close code `1008` | Application policy violation |
| Post-upgrade | Close code `1009` | Message too big |
| Post-upgrade | Close code `1011` | Unexpected server condition |
| Post-upgrade | Close code `1013` | Try again later per supporting protocol convention |
| Post-upgrade | Browser reports `1006` | Abnormal closure; **not a code sent inside a close frame** |

**Never try returning HTTP `401` after the server has sent `101`.** At that stage, use a designed close frame/protocol response or tear down the connection properly. Browsers may only surface "WebSocket connection failed" instead of exposing HTTP error status/details to the constructor; check DevTools Network handshakes and server-side logs for the root cause.

### 101 Does Not Mean Business Authorization Succeeded

A `101` only proves the WebSocket connection succeeded at the protocol layer. The backend can still reject messages/subscriptions and send close `1008` afterward. Tests must verify **both handshake and message authorization**.

## 13. CORS Cannot Fix WebSocket Origin Policy

A common misconfiguration:

```yaml
spring:
  cloud:
    gateway:
      globalcors:
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - https://app.example.test
            allowedMethods:
              - GET
              - POST
```

This config governs **CORS for browser fetch/XHR HTTP requests**. It **must not be treated as an automatic guarantee** that WebSocket handshakes from unknown Origins are blocked per policy.

For WebSocket:

- Enforce Origin per handshake policy at ingress/Gateway and/or backend.
- Authenticate sessions/tokens/tickets separately.
- Check permissions per room/tenant/topic.
- Never rely on `Access-Control-Allow-Origin` for browser self-protection as with REST APIs.
- Never enable wildcard Origin with cookies/sessions just to "make the connection work."
- Never treat CORS `OPTIONS` preflight as a prerequisite of the browser WebSocket API.

A `403` returned by the WebSocket Origin guard may be **the intended security behavior**. Do not delete Origin validation to fix a handshake error before verifying the frontend origin is genuinely trusted.

## 14. Spring Security, CSRF, and Cross-Site Requests

For apps using **session cookies**, browsers may attach cookies automatically on WebSocket handshakes when cookie policies permit, creating the CSWSH risk described in section 5.

### Why Might an HTTP CSRF Filter Be Insufficient?

State-changing HTTP operations over `POST/PUT/PATCH/DELETE` are normally guarded by CSRF tokens with cookie-based sessions. However, an HTTP/1.1 WebSocket handshake is a **GET Upgrade**, and **subsequent messages do not pass through HTTP CSRF filters like POSTs**.

Therefore, never assume Security's default `csrf()` thoroughly checks every socket message. You need an Origin allowlist, authentication, message/resource authorization, and potentially CSRF tokens/handshake tickets or protocol-specific policies.

If using STOMP and your framework supports protecting CONNECT with CSRF tokens, configure it properly for the **message layer**; do not confuse it with CORS headers.

### SameSite Cookies

- `SameSite=Strict` can restrict cookies in cross-site scenarios per browser behavior.
- `SameSite=Lax` still does not prevent every WebSocket CSWSH scenario.
- `SameSite=None; Secure` may be needed for legitimate cross-site designs, increasing reliance on Origin validation and browser cookie policies.
- "Same-site" and "same-origin" are distinct; two subdomains can be same-site while cross-origin.

In every case, **the server must enforce permissions independently of cookie attributes**.

## 15. Ingress and Reverse Proxy: Upgrade, Origin, and TLS

Gateway routes and security may be completely right while browsers still fail to connect if ingress lacks WebSocket Upgrade support or alters headers incorrectly.

### Components to Verify

| Configuration point | Common mistake | Consequence |
| --- | --- | --- |
| HTTP/1.1 Upgrade support | Proxy strips `Upgrade`/`Connection` | No 101, handshake fails |
| Proxy/read idle timeout | Drops connection after idle period | Sockets drop repeatedly |
| TLS termination | Wrong HTTP/HTTPS/WS/WSS scheme | Browser blocks mixed content or TLS errors |
| SNI/hostname verification | Backend `wss://` mismatches cert | Outbound handshake fails |
| `Origin` preservation | Proxy strips/rewrites Origin | Origin allowlist rejects or gets bypassed |
| `Host`/Forwarded headers | Trusting client-set `X-Forwarded-Host` | Wrong public URL/tenant, host spoofing |
| Connection draining | Pod killed without draining | Mass disconnects |
| WAF/request limits | Blocks Upgrade/subprotocols or long URIs | 403/4xx before Gateway |
| WebSocket compression/frame sizes | Incompatible extensions/limits | 101 followed by framing/size errors |

**Never rely on client-supplied `X-Forwarded-Proto: https`** to deem a request secure; trust only forwarded headers injected by configured trusted proxies. If the public target is `wss://` and the internal hop is `ws://`, confirm that is an approved security choice, not an accidental downgrade.

### NGINX Hop-by-Hop WebSocket Snippet

```nginx
# Illustrates HTTP/1.1 Upgrade specifically when using NGINX.
# Location, upstream, TLS, and auth configs must fit real deployment.
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name api.example.test;

    location /ws/ {
        proxy_pass http://gateway_internal;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header Origin $http_origin;
        proxy_read_timeout 3600s;
    }
}
```

This is an **illustrative snippet**, omitting certificate directives, authentication, error handling, rate limits, and real upstream setup. Never copy it as a complete NGINX config. `Origin` should be preserved/validated per policy; never rewrite it to an "allowed" Origin, which defeats tracking where requests originated.

## 16. WebSocket Rate Limiting: Handshake and Frames Are Two Problems

Gateway's HTTP rate limiter typically operates at the **HTTP request level**. An open WebSocket connection can emit thousands of messages after one handshake, and those subsequent frames **do not traverse the HTTP request rate-limiting pipeline like thousands of separate GETs**.

Two layers are therefore required:

1. **Handshake admission:** limit new connection openings per principal/IP/tenant, checking auth and Origin before upgrade.
2. **Active connection/message controls:** cap concurrent sockets, frame/message sizes, send rates, subscriptions, and buffered outbound messages.

| Goal | Is `RequestRateLimiter` on handshake alone enough? |
| --- | --- |
| Cap new socket openings per second | Helpful if the filter actually sits on the handshake route |
| Cap 10,000 messages/second on one socket | **No** |
| Prevent one user from opening too many sockets | Needs active-connection accounting |
| Block publishing to unauthorized topics | Needs message-level authorization |
| Stop slow outbound consumers from exhausting memory | Needs backpressure/buffer/close policies |
| Prevent post-deploy reconnect storms | Handshake limits + jitter/backoff + draining |

An `lb:ws://` route after 101 needs connection capacity planning; HTTP request QPS does not reflect active WebSocket session counts.

## 17. Retry and Circuit Breakers with WebSocket

### Cannot "Retry Every Frame" Like REST

Gateway's `Retry` `GatewayFilterFactory` targets **HTTP request/response attempts**. For WebSocket:

- A handshake rejected with `401/403` should normally **not** immediately retry the same request.
- If upstream fails to connect before upgrade, the client can retry per its own policy.
- After `101`, a socket lost mid-message cannot be "replayed in full" by retrying an HTTP request while preserving protocol semantics.
- A message already processed by the backend may lose its ACK; reconnecting and resending risks duplicate side effects.

You need **application-level reconnects, acks/sequence numbers, idempotency, and replay windows** per protocol. Never add `Retry` to a WebSocket route assuming it delivers messages exactly-once.

### CircuitBreaker Helps Within Limits

A circuit breaker can protect **handshake/upstream connects** when integrated cleanly at the failure boundary, yet errors on long-lived WebSocket connections may not match HTTP handshake outcomes. Timeouts, close codes, and network resets need dedicated instrumentation.

When a breaker is OPEN, an HTTP `503` JSON fallback may cleanly report a **failed handshake**, yet cannot replace a live WebSocket server continuing to push frames. Document the client contract on connection failure.

### Service Discovery and Sticky State

A WS connection can hold local state on instance B. On reconnect, LoadBalancer may pick instance C. If the protocol requires preserving session/topic state, store state out-of-process (broker, Redis, durable streams...) or design authenticated session resumption. **Do not assume Gateway automatically provides sticky routing** solely because the session cookie matches.

## 18. Observing Handshakes Without Leaking Credentials

For diagnostics, capture at least these fields:

| Data | Value |
| --- | --- |
| Timestamp and trace/correlation ID | Correlate frontend, Ingress, Gateway, and backend |
| Gateway replica/pod ID | Identify which node handled the socket |
| Route ID | `chat-websocket` or another route? |
| Public path/Host, HTTP method | Did route predicates match? |
| Incoming `Origin` (canonicalized, controlled) | Permitted or rejected by policy? |
| Authentication result | Valid principal or not; **never log tokens/cookies** |
| Checked tenant/resource context | Did the user enter the right room/tenant? |
| Handshake HTTP status | `101` or `401/403/404/502/503` |
| Upstream service ID/selected instance | Where did it proxy? |
| TLS/proxy error category | SSL handshake/timeout/Upgrade mismatch |
| Active connections and close code | How long did the socket live, and why did it close? |
| Reconnect rate and message rate | Spot reconnect storms/abuse |

**Never log** raw `Cookie`, `Authorization`, handshake tickets, full query strings containing tickets, WebSocket payloads carrying personal data, or raw session IDs. When debugging a specific user, use anonymized/protected IDs with proper auditing.

### Metrics That Do Not Substitute for Each Other

- **HTTP 101 count:** successful upgrade handshakes.
- **Active connections gauge:** currently open sockets.
- **Handshake rejection count:** 401/403/404/5xx before upgrade.
- **Close-code distribution:** how sockets terminate after upgrade.
- **Message throughput/latency:** post-upgrade protocol behavior.
- **Authorization-denied messages:** not equivalent to handshake failures.

An HTTP access log showing `101` does not prove the client subscribed to the right room, and spikes in `1006` do not automatically prove Origin mismatches; trace across layers.

## 19. Testing with Browser DevTools

Browsers are ideal for testing browser-specific restrictions:

```javascript
const socket = new WebSocket(
  "wss://api.example.test/ws/chat/rooms/42",
  ["chat.v1"]
);

socket.onopen = () => console.log("OPEN");
socket.onmessage = event => console.log("MESSAGE", event.data);
socket.onerror = () => console.log("ERROR");
socket.onclose = event =>
  console.log("CLOSE", event.code, event.reason, event.wasClean);
```

In DevTools → Network → WS, inspect:

1. Request URL, `wss` scheme, path, host.
2. `Origin` of the active page.
3. Whether eligible cookies are sent (mask values before sharing screenshots).
4. `Upgrade`, `Connection`, and `Sec-WebSocket-Protocol`.
5. Status `101` vs. error response.
6. Post-101 frames/messages and close events.
7. Whether the response includes `Sec-WebSocket-Accept`/server-chosen protocol.
8. Any related requests, login redirects, or HTTP errors.

**The browser API does not let JavaScript read full HTTP handshake error details.** Use Network traces and Ingress/Gateway/backend logs to see statuses rather than relying solely on `socket.onerror`.

### Credentials Reminder

Do not pass a `headers` argument to the browser `WebSocket` constructor; the API does not support it. If session cookies are missing, inspect Domain/Path/SameSite/Secure and origin/site differences instead of trying to inject a `Cookie` header via JavaScript.

## 20. Preliminary HTTP Upgrade Testing with curl

You can send an HTTP/1.1 handshake to **observe response status and headers**:

```bash
curl --http1.1 -i --max-time 5 \
  -H 'Host: api.example.test' \
  -H 'Origin: https://app.example.test' \
  -H 'Connection: Upgrade' \
  -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  https://api.example.test/ws/chat/rooms/42
```

The `Sec-WebSocket-Key` value in the example is a public test string, **not** a token. If the server accepts, you may see `101` followed by curl timing out; **a timeout after 101 is not a handshake failure**.

`curl` **is not a full WebSocket client** for testing bidirectional frames, ping/pong, and subprotocol messaging. Use a browser, `wscat`, `websocat`, or an appropriate test client to verify connection lifecycles and message flows. Never paste real session cookies onto shell command lines saved in history.

### Do Not Confuse Origin with Host

`Host` in the example is the Gateway target; `Origin` is the page source. Never pass `Origin: https://api.example.test` just to make a test pass if the real frontend runs at `https://app.example.test`. A test faking a "matching" Origin unlike real traffic masks allowlist bugs.

## 21. Integration Tests with Spring WebFlux and WebSocket Clients

Good tests must prove:

- Handshake from an allowed Origin + valid identity → socket succeeds.
- Disallowed Origin → **rejected before 101**.
- Unauthenticated or invalid token/ticket → **fails**.
- Valid identity on wrong tenant/room → rejected at handshake or message level per contract.
- Post-101, send/subscribe permissions are still enforced.
- Upstream receives the **intended** path, subprotocol, and identity, never spoofed headers.

### Test Client Using `ReactorNettyWebSocketClient`

```java
@Test
void validOriginCanOpenSocket() {
    ReactorNettyWebSocketClient client =
        new ReactorNettyWebSocketClient();

    HttpHeaders headers = new HttpHeaders();
    headers.setOrigin("https://app.example.test");
    headers.set("Cookie", "SESSION=<test-session-value>");

    URI uri = URI.create(
        "ws://localhost:8080/ws/chat/rooms/42");

    StepVerifier.create(
            client.execute(uri, headers, session ->
                session.send(Mono.just(
                    session.textMessage("ping")))
                    .then(session.receive().next())
                    .then()))
        .verifyComplete();
}
```

This test is an **illustrative skeleton**; it needs a valid test session store, a WebSocket backend stub, imports, version-matched APIs, and an echo/response server. The cookie value is a test placeholder, not a server-issued session. **Do not treat it as a complete authentication test** unless you genuinely issue a session/principal and verify permissions.

### Testing Rejected Origins

```java
@Test
void disallowedOriginCannotCompleteHandshake() {
    ReactorNettyWebSocketClient client =
        new ReactorNettyWebSocketClient();

    HttpHeaders headers = new HttpHeaders();
    headers.setOrigin("https://evil.example.test");

    URI uri = URI.create(
        "ws://localhost:8080/ws/chat/rooms/42");

    StepVerifier.create(
            client.execute(uri, headers, session ->
                Mono.empty()))
        .expectError()
        .verify();
}
```

This test only illustrates a failed handshake; in real runs assert **HTTP 403** (or the defined status), confirm upstream request count **equals 0**, and verify rejection happened at the Origin guard before upgrade. A TCP error also passes `expectError()` without proving the Origin policy works; check the error type/status or stub/layer logs specifically.

### Using Spring Security WebTestClient

`WebTestClient` works well for testing **HTTP policies and handshake rejections** in some fixtures, while a real WebSocket client is needed for **full WebSocket frame exchanges**. Never write `webTestClient.get().exchange().expectStatus().isOk()` as a passing WebSocket test, since valid handshakes return `101`, not HTTP `200`.

## 22. Comprehensive Test Matrix

| ID | Input / scenario | Expectation |
| --- | --- | --- |
| T1 | Valid browser origin, valid login session | Handshake 101, socket opens |
| T2 | Unknown browser origin, valid session | Rejected pre-upgrade, not proxied upstream |
| T3 | Missing Origin under browser-only policy | Rejected or handled per documented policy |
| T4 | No cookie/session | 401/redirect per auth contract, no 101 |
| T5 | Expired cookie | Not treated as logged-in user |
| T6 | Cookie `SameSite`/`Path` mismatch | Browser omits cookie; debug cookie policy properly |
| T7 | BFF login then open WebSocket | Right principal without JS adding Authorization |
| T8 | Non-browser sends valid Bearer token | Security verifies and grants scoped permissions |
| T9 | Non-browser spoofs Origin without auth | Denied access |
| T10 | Query carries long-lived access token | Policy rejects unsafe design |
| T11 | Valid one-time ticket | Single-use only, TTL/resource bound |
| T12 | Reused/expired ticket | Cannot reopen socket |
| T13 | User in tenant Alpha opens Beta room | Rejected by permissions |
| T14 | User in room sends message to admin topic | Message-level authz denies |
| T15 | User logs out/revoked after 101 | Server enforces recheck/close policy |
| T16 | Unsupported `Sec-WebSocket-Protocol` | Handshake/negotiation handled per protocol |
| T17 | Ingress strips `Upgrade` | Fails to upgrade; identifies proxy bug |
| T18 | Ingress alters/strips `Origin` | Origin policy cannot be bypassed |
| T19 | Upstream `lb:ws://` has no instances | Distinguishes discovery/no-instance from auth failure |
| T20 | Invalid backend WSS certificate | TLS verification rejects; never bypassed |
| T21 | Gateway route wrong `StripPrefix` | Test catches upstream path mismatch |
| T22 | WebSocket route requires `Method=POST` | HTTP/1.1 GET handshake fails to match |
| T23 | Multiple Gateway replicas with local session store | Exposes intermittent 401 on login/sockets |
| T24 | Backend instance drained | Active sockets close, clients reconnect with backoff |
| T25 | Many clients reconnect simultaneously | Handshake rate/active sockets controlled |
| T26 | Oversized message / slow consumer | Size/buffer limits and close policy enforced |
| T27 | HTTP 101 yet message authz fails | Not mistaken for blanket topic access |
| T28 | Client cancels mid-handshake | No leaked resources/subscriptions |
| T29 | `TokenRelay` configured on WS route | Verifies exact header/token received by backend per version |
| T30 | JWT/permissions revoked | Stops delivering private data indefinitely |

Security testing must cover **negative cases**. A socket working along the happy path says nothing about CSWSH, cross-tenant leaks, or stale session permissions.

## 23. Runbook When WebSocket Fails to Connect Through Gateway

### Symptom: Browser Reports "WebSocket connection failed"

Follow in order:

1. **Check Network → WS:** Did the request fire? Are the `ws`/`wss` scheme and host/path right?
2. **Check handshake HTTP status:** `101`, `401`, `403`, `404`, `502`, `503`, or redirect?
3. **If 401/redirect:** are cookie/session/JWT/ticket valid; did the browser actually send the cookie?
4. **If 403:** did Origin allowlist, tenant/room authorization, WAF, or Security policy reject it?
5. **If 404:** did route `Path`/`Method` match, is `lb:ws://` right, did `StripPrefix` break the path?
6. **If 502/503/504:** inspect instance discovery, backend WS handler, TLS trust/hostname, TCP connect, and response timeout.
7. **If no Upgrade/101:** verify Ingress supports HTTP/1.1 WebSocket Upgrade and hop-by-hop headers.
8. **If 101 then immediate close:** check subprotocol, message auth, close code, broker subscription, and server exceptions.
9. **If failing only for certain users/replicas:** compare `WebSession`/authorized client stores, cookie attributes, origin/path configs, and Gateway replicas.
10. **If failing after a long duration:** check proxy idle timeouts, ping/pong, session expiry, permission revocation, pod draining, and connection capacity.
11. **After fixing:** re-run tests for allowed/disallowed origins, anonymous callers, tenant boundaries, 101, messages, and reconnects.

### Quick Diagnostic Table

| Symptom | Where to look first | What to avoid |
| --- | --- | --- |
| WebSocket `401` while REST login works | Cookie scope/SameSite, route Security context | Stuffing raw tokens into URLs |
| WebSocket `403` on unknown Origin | Origin allowlist and CSWSH policy | Switching to wildcard without assessing trust |
| HTTP CORS enabled yet WS still fails | WebSocket Origin policy/handshake | Assuming CORS preflight protects WS |
| Never reaches `101` | Ingress Upgrade/TLS/Gateway route | Merely bumping retries |
| `101` then `1008` | Message authz/subprotocol policy | Assuming a 101 handshake proves full security |
| Works on one Gateway replica, 401 on another | Shared `WebSession`/store, sticky routing | Ignoring session architecture |
| `lb://` route works yet WebSocket fails | `lb:ws://` scheme, routing filter | Immediately blaming service discovery |
| WSS certificate error | TLS/SNI/trust chain | Disabling certificate verification |
| WS drops during deploy | Draining and reconnect protocol | Expecting connections to auto-migrate pods |
| User Alpha sees tenant Beta's messages | Resource/message authorization | Fixing only Origin |
| Fails only after long idle | Proxy idle timeout, ping/pong, session lease | Setting infinite timeouts without load testing |
| Expired token yet socket still gets data | Long-lived authorization/revocation | Checking JWT only at handshake |

## 24. Case Study Exercise: Multi-Tenant Chat Behind Gateway

A SaaS platform has:

- Frontend at `https://app.example.test`.
- Public WebSocket endpoint `wss://api.example.test/ws/chat/rooms/{roomId}`.
- Spring Cloud Gateway Server WebFlux running multiple replicas.
- Spring Security OAuth2 login storing sessions server-side; browser uses `SESSION` cookie.
- Backend `chat-service` running multiple instances behind `lb:ws://chat-service`.
- Each room belongs to one tenant; users may read/send messages only in authorized rooms.
- A subdomain where customers host their own content: `https://pages.example.test`.

### Requirement A — Route Configuration

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: chat-websocket
          uri: lb:ws://chat-service
          predicates:
            - Path=/ws/chat/**
            - Method=GET
          filters:
            - StripPrefix=1
```

Verify `/ws/chat/rooms/42` becomes `/chat/rooms/42` at the backend and confirm the backend handles that exact path. Having `Method=GET` grants no access rights; Security and Origin guards are separate requirements.

### Requirement B — Origin Allowlist

Allow only `https://app.example.test` and controlled operator frontends. **Never** include `https://pages.example.test` because customers can upload their own JavaScript there. With cookie sessions, prevent that site from abusing another user's permissions to open private sockets.

### Requirement C — Session

Design a shared session store or clear session continuity across Gateway replicas. Cookies must set `Secure`/`HttpOnly` and proper `SameSite`; never put session IDs in URLs. On user logout, enforce a policy to close sockets or halt message delivery for the revoked identity.

### Requirement D — Authorization

Even after a `101` handshake succeeds, the backend must verify the user belongs to the tenant owning room 42, holds SUBSCRIBE/SEND permissions, and cannot switch destinations to access another room. If permissions are revoked, subscriptions/sockets must follow the revocation policy.

### Requirement E — Operations

Track active connection counts per Gateway replica, handshake successes/rejections, `Origin` allows/denies, HTTP 101s, close codes, reconnect rates, selected backend instances, and message failures. Never log cookies, tokens, or sensitive chat contents.

### Self-Check Questions

1. How do `Sec-WebSocket-Key` and `Authorization` differ in purpose?
2. Why can't JavaScript `new WebSocket(url, {headers: ...})` attach a Bearer header?
3. Does a browser send a CORS `OPTIONS` preflight before a WebSocket handshake like `fetch`?
4. Why isn't `Access-Control-Allow-Origin` enough to protect WebSocket?
5. How does CSWSH exploit session cookies and a missing Origin policy?
6. Does a valid Origin prove the user is logged in?
7. Why must tenant/room permissions still be checked even after `.authenticated()` passes?
8. How do `WebSession` and `WebSocketSession` differ?
9. Once `101` is sent, can you return another HTTP `401` to reject a message?
10. Can a server send `1006` directly inside a close frame?
11. Why isn't a plain HTTP GET client a complete WebSocket test?
12. With `lb:ws://`, does LoadBalancer pick a different instance for each frame?
13. Why do proxy `Upgrade`/`Connection` headers need explicit HTTP/1.1 support?
14. What happens when cookie `SameSite`/`Path` prevents the browser from sending it during handshake?
15. Why doesn't an expired HTTP session automatically kill an open WebSocket?
16. Should `TokenRelay` on a WebSocket route be assumed to propagate audience-correct tokens automatically?
17. Why doesn't adding `Retry` guarantee exactly-once WebSocket message delivery?
18. Which metrics separate pre-`101` handshake errors from post-`101` message errors?
19. How many `WebSocketSession` instances vs. HTTP sessions might a user with two open tabs have?
20. When a client reconnects after a rolling deploy, how do you avoid duplicate business messages or broken permissions?

**Takeaway:** WebSocket begins as an **HTTP handshake**, so principal authentication, **Origin allowlist** checks, and resource authorization must happen **before `101 Switching Protocols`**; after upgrade, every message/topic still needs authorization and connection-lifetime policies. Because the browser WebSocket API prohibits arbitrary Authorization headers, consider **session cookies/BFF** or **one-time short-lived tickets** alongside CSWSH protection. In Spring Cloud Gateway, properly routing `ws/wss`/`lb:ws://`, proxying Upgrade/TLS cleanly, managing `WebSession`/`WebSocketSession`, testing multi-tenant boundaries, and monitoring reconnects/close codes yield a secure WebSocket gateway.
