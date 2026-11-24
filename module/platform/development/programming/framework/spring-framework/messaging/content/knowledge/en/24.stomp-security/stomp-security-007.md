# Same-Origin, CSRF, and SockJS Security Configuration

In a Spring application using STOMP over WebSocket, security must govern both the initial connection and the frames sent after connecting. Three mechanisms that are frequently confused are **Same-origin**, **CSRF**, and **CORS**. They address different problems:

- **Origin validation** restricts which websites are permitted to initiate a WebSocket or SockJS connection from a browser.
- **CSRF protection** requires proof that a valid same-origin page can obtain before opening a STOMP session.
- **Message authorization** decides which destinations a user is permitted to send frames to and which destinations they may subscribe to.

SockJS adds a point to watch: when WebSocket is unavailable, it can fall back to HTTP transports such as XHR streaming or polling. Those HTTP requests pass through the Spring Security filter chain, so the SockJS endpoint needs dedicated configuration while still preserving CSRF checking on the STOMP CONNECT frame.

## 1. Why does WebSocket need Same-origin protection?

The browser's same-origin policy applies to many APIs such as reading responses from another origin, but browsers do not automatically block a cross-origin page from opening a WebSocket to a server. If a user is logged into a website using cookies, a malicious website could attempt to open a WebSocket to that website. Session cookies may be sent by the browser along with the handshake depending on cookie and request policies.

This attack scenario is commonly called **Cross-Site WebSocket Hijacking (CSWSH)**:

1. The user logs into https://bank.example.
2. The browser holds the login session cookie.
3. The user opens an untrusted page, for example https://evil.example.
4. That page attempts to open a WebSocket to wss://bank.example/ws.
5. If the server accepts the connection based on the cookie without checking the origin and without requiring CSRF proof, the malicious page can perform actions under the user's session.

When a WebSocket handshake is sent, browsers typically include the Origin header. The server must inspect this value. Since version 4.1.5, Spring Framework accepts only same-origin requests by default for WebSocket and SockJS. An explicit list of allowed origins can be configured when the frontend and backend genuinely run on different origins.

An origin consists of scheme, host, and port. For example, https://app.example.com is a different origin from http://app.example.com or https://app.example.com:8443.

**Origin is not authentication.** Non-browser clients can set the Origin header themselves. Therefore, an allowlist protects browsers from cross-origin connections but does not replace authentication, CSRF, or authorization.

## 2. Restricting origins on the WebSocket endpoint

For endpoints used only on the same origin, you can keep Spring's default:

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/chat").withSockJS();
    }
}
```

If the frontend is hosted on another origin, declare the exact allowed origins:

```java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/chat")
            .setAllowedOrigins("https://app.example.com")
            .withSockJS();
}
```

You can pass multiple origins or use setAllowedOriginPatterns(...) when patterns are genuinely needed. Prefer an explicit list of origins. Never configure a wildcard in production merely to work around handshake errors. In particular, CORS does not normally allow combining a wildcard origin with credentials.

When origins are restricted, some iframe-based SockJS transports that cannot verify the origin are disabled. This affects legacy browsers and fallback choices. Confirm which transports your clients actually need before changing the allowlist.

## 3. CSRF token on STOMP CONNECT

Spring Security integrates STOMP protection via @EnableWebSocketSecurity. By default, every inbound CONNECT frame must carry a valid CSRF token. This adds a verification layer after origin validation: only a page able to obtain a valid CSRF token can open a STOMP session.

The token is placed in the **STOMP CONNECT headers**, not in the payload of a SEND frame. When a client uses a JavaScript STOMP library, these headers are usually passed via the connectHeaders property or the headers argument of connect, depending on the library version.

### Message authorization configuration

The example below uses Spring Security 5.8+'s AuthorizationManager API:

```java
@Configuration
@EnableWebSocketSecurity
public class WebSocketSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages
    ) {
        messages
                .nullDestMatcher().authenticated()
                .simpDestMatchers("/app/**").hasRole("USER")
                .simpSubscribeDestMatchers("/topic/public").permitAll()
                .simpSubscribeDestMatchers("/user/**").hasRole("USER")
                .simpTypeMatchers(
                        SimpMessageType.MESSAGE,
                        SimpMessageType.SUBSCRIBE
                ).denyAll()
                .anyMessage().denyAll();

        return messages.build();
    }
}
```

Rules are evaluated in order:

- Messages without a destination, including CONNECT, require an authenticated user. @EnableWebSocketSecurity simultaneously enforces CSRF token validation for CONNECT.
- SEND to /app/** requires role USER.
- Clients may subscribe to /topic/public under the example's public policy.
- Subscribing to /user/** requires role USER.
- Remaining MESSAGE or SUBSCRIBE frames are denied.
- anyMessage().denyAll() closes by default so new destinations are not accidentally exposed.

In a real application, adjust the destination list and roles to match business requirements. Do not let clients SEND directly to broker prefixes such as /topic/** or /queue/** if clients should only send commands to the application prefix. You must also protect SUBSCRIBE: Spring Security primarily protects clientInboundChannel and does not filter individual messages on clientOutboundChannel. Restricting who can subscribe is a crucial safeguard against reading another user's data.

Commonly used imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;
```

## 4. Obtaining the CSRF token for the client

For pages rendered by server-side templates, the CSRF token can be read from the _csrf request attribute. For static frontends or SPAs, a common approach is to provide an HTTP endpoint returning the current token.

```java
@RestController
public class CsrfController {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}
```

This endpoint must follow the application's authentication and caching policies. Never let a CDN or shared cache store one user's token and serve it to another user. The frontend fetches the token via a same-origin request and then attaches it to the STOMP CONNECT headers.

Example with @stomp/stompjs and SockJS:

```javascript
import { Client } from "@stomp/stompjs";
import SockJS from "sockjs-client";

async function createStompClient() {
    const response = await fetch("/csrf", {
        credentials: "same-origin",
        cache: "no-store"
    });

    if (!response.ok) {
        throw new Error("Cannot obtain CSRF token");
    }

    const csrf = await response.json();

    const client = new Client({
        webSocketFactory: () => new SockJS("/chat"),
        connectHeaders: {
            [csrf.headerName]: csrf.token
        },
        onConnect: () => {
            client.subscribe("/topic/public", frame => {
                console.log("Message:", frame.body);
            });
        },
        onStompError: frame => {
            console.error("STOMP error:", frame.headers["message"]);
        }
    });

    client.activate();
    return client;
}
```

In the example, webSocketFactory selects the SockJS transport. If the server uses plain WebSocket, you can use brokerURL with wss://app.example.com/chat instead of the factory. The token is placed in CONNECT headers so Spring Security checks it when receiving the CONNECT frame.

When the token expires, changes after login/logout, or the session is refreshed, the frontend must fetch a new token before reconnecting. Never hard-code a CSRF token into a JavaScript bundle because the token must be bound to the current user session.

## 5. SockJS and the HTTP CSRF filter

SockJS can use HTTP requests for transport fallbacks. For HTTP-based transports, the connection process may use POST. These requests pass through the HTTP security filter chain before Spring SockJS handles them.

There is an important distinction:

- @EnableWebSocketSecurity checks the CSRF token on the **STOMP CONNECT frame**.
- CsrfFilter protects **HTTP requests** according to the web security configuration.

With SockJS, application tokens cannot always be placed in arbitrary HTTP headers on every transport request in the same way as regular XHR. Spring Security advises ignoring the HTTP CSRF filter specifically for the SockJS endpoint path while retaining token validation on STOMP CONNECT headers.

For example, if the endpoint is /chat:

```java
@Configuration
@EnableWebSecurity
public class HttpSecurityConfig {

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {

        http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/chat/**", "/csrf").authenticated()
                        .anyRequest().authenticated()
                )
                .csrf(csrf -> csrf
                        // SockJS HTTP transports are protected by the
                        // CSRF token on the STOMP CONNECT frame.
                        .ignoringRequestMatchers("/chat/**")
                )
                .headers(headers -> headers
                        // Required only when iframe-based SockJS
                        // transports must be supported.
                        .frameOptions(frame -> frame.sameOrigin())
                );

        return http.build();
    }
}
```

Key points to keep right:

1. Exclude only /chat/** from the HTTP CSRF filter because these are the SockJS transport URLs.
2. Never call csrf.disable() for the entire application. Form POSTs, state-changing APIs, and other HTTP requests still require CSRF protection per application policy.
3. Do not remove @EnableWebSocketSecurity; removing it means the example above would no longer check CSRF tokens on STOMP CONNECT by default.
4. The /chat/** path still requires authentication and origin validation. Bypassing the HTTP CSRF filter does not mean permitting anonymous or cross-origin connections.

If the application uses plain WebSocket exclusively and does not use SockJS HTTP fallback, the /chat/** exception for SockJS POST transports is unnecessary. Spring Security's CONNECT CSRF protection still applies when @EnableWebSocketSecurity is enabled.

## 6. X-Frame-Options and SockJS iframe transports

Some legacy SockJS fallbacks use an iframe to host the transport environment. Spring Security sets clickjacking protection by default, which can block content from being embedded in an iframe. If same-origin iframe transports need to be supported, you can configure:

```java
.headers(headers -> headers
        .frameOptions(frame -> frame.sameOrigin())
)
```

The X-Frame-Options: SAMEORIGIN header allows a page to be framed by the same origin while still blocking frames from other origins. Enable this only when transports actually require iframes. When allowed origins are restricted, Spring may disable iframe-based transports because those transports do not verify request origins in the required way.

Never use frameOptions.disable() just to make SockJS work. Disabling frame protection completely widens the clickjacking surface of other pages in the application. If the application already uses Content Security Policy, also check the frame-ancestors directive because it likewise determines which pages may embed content.

## 7. CORS for SockJS and allowed origins

CORS and allowed origins are related but not identical:

| Mechanism | What does it check? | Scope |
|---|---|---|
| WebSocket allowed origins | Origin header of the handshake | WebSocket and SockJS endpoints |
| CORS | Origin, method, and headers of HTTP requests | SockJS XHR streaming/polling and HTTP APIs |
| CSRF | Token proving the request comes from a page authorized to obtain the token | HTTP requests and STOMP CONNECT depending on configuration |
| Message authorization | Which destinations a user can SEND/SUBSCRIBE to | STOMP inbound messages |

For SockJS XHR streaming and polling, Spring automatically adds CORS headers if the response does not already contain other CORS headers. If the application already configures CORS via a Servlet Filter or Spring MVC, avoid emitting two conflicting sets of CORS headers. Check preflight requests, cookie credentials, and the list of allowed headers.

If the frontend is on a different origin and must send session cookies, configure an explicit origin, an appropriate credential policy, and SameSite/Secure cookies matching the environment. Never use a wildcard origin with credentials. CORS only allows browsers to send/read certain HTTP requests; it does not replace CSRF tokens or STOMP message authorization.

## 8. Authentication, Origin, and CSRF do not replace each other

With STOMP over WebSocket, Spring typically uses the authenticated Principal from the HTTP handshake. If Spring Security has authenticated the HTTP request, that user is attached to the WebSocket/SockJS session and subsequent STOMP messages.

The login and passcode headers of STOMP CONNECT were originally designed for STOMP over TCP. Spring does not use them by default as the authentication mechanism for STOMP over WebSocket. Authenticate at the HTTP layer or build a dedicated token mechanism on the inbound channel when explicitly required.

Four questions must be answered independently:

- **Who is connecting?** HTTP authentication and Principal.
- **Which pages are permitted to open connections from a browser?** Origin allowlist.
- **Was the connection opened by a page authorized to obtain the token?** CSRF token on STOMP CONNECT.
- **What can the user do after connecting?** Message authorization for SEND and SUBSCRIBE.

A valid origin does not mean the user is allowed to subscribe to every destination. A valid CSRF token also does not mean the user is allowed to send administrative commands.

## 9. Verifying security configuration

Test both success paths and rejection paths:

1. Open the application from an allowed origin and verify the WebSocket/SockJS handshake succeeds.
2. Test from a different origin and verify the server rejects the handshake or transport request.
3. Send STOMP CONNECT without a CSRF token and verify Spring Security rejects it.
4. Send CONNECT with a valid token for the current session and verify the session is established.
5. Test a missing token, an invalid token, and a token from another session; all must be rejected.
6. With SockJS, verify HTTP POST requests to the transport path are not blocked by the HTTP CSRF filter before STOMP CONNECT is checked.
7. Verify HTTP POST requests outside /chat/** still require a CSRF token.
8. Verify a user without sufficient roles cannot SEND to /app/** or SUBSCRIBE to private destinations.
9. Verify a client cannot SEND directly to /topic/** to spoof server-emitted messages.
10. If using iframe fallback, verify same-origin frames work and frames from other origins are blocked.

In logs, distinguish an HTTP 403 at handshake/transport from a STOMP CONNECT failure. Both errors may surface as “cannot connect” on the client, yet they happen at two different layers.

## 10. Common configuration mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming browsers automatically block cross-origin WebSockets | Can expose CSWSH when using cookie sessions | Validate Origin on the server and require CSRF tokens |
| Enabling CORS alone without checking WebSocket Origin | WebSocket handshakes may remain unprotected as intended | Configure allowed origins on the STOMP endpoint |
| Disabling all HTTP CSRF so SockJS POST works | Other HTTP forms/APIs become vulnerable to CSRF | Ignore only the SockJS transport path |
| Ignoring /chat/** and also removing STOMP CONNECT CSRF | Connections lacking a token may be accepted | Keep @EnableWebSocketSecurity and CONNECT tokens |
| Sending the CSRF token in a SEND payload | Interceptor does not see the token in CONNECT headers | Put the token in STOMP CONNECT headers |
| Allowing wildcard origins when cookies are used | Any website can attempt to connect | Use an explicit allowlist |
| Enabling frameOptions.disable() | Increases clickjacking risk | Use SAMEORIGIN only when iframe fallback is required |
| Trusting Origin as client identity | Non-browser clients can forge the header | Enforce authentication and authorization independently |

## References

- [Spring Security 6.5 — WebSocket Security](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html)
- [Spring Framework 6.2 — WebSocket Allowed Origins](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/server.html)
- [Spring Framework 6.2 — SockJS Fallback and CORS](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/fallback.html)
- [Spring Framework 6.2 — STOMP Authentication](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authentication.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
