# Token Authentication via ChannelInterceptor When Appropriate

## Objective

With STOMP over WebSocket, Spring needs to know which user owns a messaging session before applying authorization rules to messages and subscriptions. In applications using cookies or HTTP sessions, Spring normally obtains the identity from the HTTP handshake authentication process. For stateless applications, mobile clients, or browsers that cannot send custom HTTP headers in the WebSocket handshake, an access token may need to be sent in the STOMP CONNECT frame and validated using a `ChannelInterceptor`.

This article covers:

- When to use authentication at the HTTP handshake and when to authenticate a token at STOMP CONNECT.
- How to read a Bearer token from a native STOMP header and verify a JWT.
- How to attach an `Authentication` to the session's `Principal` using `StompHeaderAccessor.setUser`.
- Interceptor ordering when integrating with Spring Security.
- How to separate authentication from authorization, protect CONNECT with CSRF, and restrict destinations.
- Common errors, testing, and security considerations when tokens are used for long-lived connections.

## 1. Where does WebSocket authentication happen?

WebSocket starts with an HTTP request to upgrade the connection. Spring Security can authenticate that request just like other HTTP requests. Spring Framework transfers the HTTP request's `Principal` to the WebSocket/SockJS session and attaches that identity to subsequent STOMP messages.

Therefore, if the application already uses cookie sessions, HTTP Basic, or Bearer tokens at the HTTP handshake in a way the client supports, there is usually no need to re-authenticate the token in STOMP CONNECT. Let HTTP security authenticate the user and then use the existing `Principal`.

However, the browser WebSocket API does not allow JavaScript to arbitrarily add headers to the HTTP handshake. Browser-side SockJS libraries also do not support sending custom HTTP headers for transport requests. Spring's Java STOMP client can send headers for both WebSocket and SockJS requests, whereas browser clients have different limitations.

When a browser or stateless application needs to use a Bearer token without being able to place the token on the HTTP handshake, the token can be passed in the **STOMP CONNECT frame**. The server reads that header with a `ChannelInterceptor` on the inbound channel, validates the token, and attaches the `Authentication` to the session.

| Option | Where is the token/identity taken from? | When suitable |
| --- | --- | --- |
| HTTP handshake authentication | Cookie, HTTP Authorization, or authenticated Principal | Application already has an HTTP session or client can send HTTP auth headers |
| STOMP CONNECT token | Native header in the CONNECT frame | Browser client needs to send a bearer token but cannot customize HTTP handshake headers |
| Broker STOMP login/passcode | Credentials at the STOMP TCP layer | Client connects directly to the broker or broker architecture requires it; not the default for browser WebSocket via Spring |

Do not send tokens via query strings just to work around header restrictions. URLs can appear in access logs, proxy logs, tracing, or monitoring tool history.

## 2. Token authentication flow via STOMP CONNECT

With token authentication, the flow typically consists of:

1. The client opens a WebSocket to the Spring endpoint.
2. The client sends STOMP CONNECT with the native header `Authorization: Bearer <access-token>`.
3. `ChannelInterceptor` receives the message on `clientInboundChannel`.
4. The interceptor performs authentication only when the STOMP command is CONNECT.
5. The interceptor reads the Bearer token and verifies it via `JwtDecoder` or the corresponding authentication mechanism.
6. When valid, the JWT is converted into an `Authentication` and `accessor.setUser(authentication)` is called.
7. Spring records the Principal for the STOMP session and attaches that user to subsequent messages in the same session.
8. Spring Security can use the authenticated user to authorize MESSAGE, SUBSCRIBE, and other inbound commands.

The core idea is to authenticate CONNECT once and attach the identity to the session. Do not take a username, role, or user ID from an arbitrary header declared by the client. The identity must be derived from a verified token or a trusted authentication system.

## 3. Client sending a Bearer token in the CONNECT frame

Example using the JavaScript library `@stomp/stompjs`:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    connectHeaders: {
        Authorization: "Bearer " + accessToken
    },
    onConnect: () => {
        client.subscribe("/user/queue/notifications", frame => {
            const notification = JSON.parse(frame.body);
            handleNotification(notification);
        });
    },
    onStompError: frame => {
        console.error("STOMP error:", frame.headers["message"]);
    }
});

client.activate();
~~~

`connectHeaders` are headers of the STOMP CONNECT frame. They are not HTTP headers of the WebSocket handshake. The server needs an interceptor to read and validate them; Spring does not automatically validate Bearer tokens in native STOMP headers by default.

If using Spring Security with `@EnableWebSocketSecurity`, CONNECT also requires a CSRF token under the default configuration. In that case, the client sends both the Bearer token and the CSRF token in the STOMP CONNECT headers:

~~~javascript
const connectHeaders = {
    Authorization: "Bearer " + accessToken
};

connectHeaders[csrfHeaderName] = csrfToken;

const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    connectHeaders,
    onConnect: () => {
        client.subscribe("/user/queue/notifications", onNotification);
    }
});
~~~

`csrfHeaderName` and `csrfToken` are obtained from the CSRF token provided by the server. A CSRF token serves a different purpose from an access token: it protects CONNECT under the Same Origin Policy, whereas the Bearer token establishes identity. Do not substitute one token for the other.

With SockJS, you can create the client using `webSocketFactory` and still pass STOMP headers via `connectHeaders`. If configuring HTTP CSRF for SockJS fallback, adjust the policy only for the required SockJS endpoints per the Spring Security guide; do not disable CSRF for the entire application.

## 4. Validating JWTs with a ChannelInterceptor

Spring Framework lets you register an interceptor on the inbound channel using `configureClientInboundChannel`. `StompHeaderAccessor` exposes the STOMP command and native headers. When the command is CONNECT, read the Authorization header, verify the JWT, convert it into an Authentication, and call `setUser`.

The example below uses `JwtDecoder` and `JwtAuthenticationConverter` from Spring Security Resource Server:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
public class StompTokenAuthenticationConfig
        implements WebSocketMessageBrokerConfigurer {

    private final JwtDecoder jwtDecoder;
    private final JwtAuthenticationConverter authenticationConverter;

    public StompTokenAuthenticationConfig(
            JwtDecoder jwtDecoder,
            JwtAuthenticationConverter authenticationConverter) {
        this.jwtDecoder = jwtDecoder;
        this.authenticationConverter = authenticationConverter;
    }

    @Override
    public void configureClientInboundChannel(
            ChannelRegistration registration) {

        registration.interceptors(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(
                    Message<?> message,
                    MessageChannel channel) {

                StompHeaderAccessor accessor =
                        MessageHeaderAccessor.getAccessor(
                                message, StompHeaderAccessor.class);

                if (accessor == null) {
                    throw new BadCredentialsException(
                            "Missing STOMP message headers");
                }

                if (StompCommand.CONNECT.equals(accessor.getCommand())) {
                    String authorization =
                            accessor.getFirstNativeHeader(
                                    HttpHeaders.AUTHORIZATION);

                    if (authorization == null) {
                        throw new BadCredentialsException(
                                "Missing Bearer token");
                    }

                    String[] parts = authorization.trim().split("\\s+", 2);
                    if (parts.length != 2
                            || !"Bearer".equalsIgnoreCase(parts[0])
                            || parts[1].isBlank()) {
                        throw new BadCredentialsException(
                                "Invalid Authorization header");
                    }

                    try {
                        Jwt jwt = jwtDecoder.decode(parts[1]);
                        Authentication authentication =
                                authenticationConverter.convert(jwt);

                        if (authentication == null) {
                            throw new BadCredentialsException(
                                    "Could not create Authentication");
                        }

                        accessor.setUser(authentication);

                        // Prevent the Bearer token from continuing through handlers
                        // as an unnecessary native header.
                        accessor.removeNativeHeader(
                                HttpHeaders.AUTHORIZATION);
                    }
                    catch (JwtException exception) {
                        throw new BadCredentialsException(
                                "Invalid or expired Bearer token",
                                exception);
                    }
                }

                return message;
            }
        });
    }
}
~~~

This is an illustrative configuration for JWT. The project needs the corresponding Spring Security Resource Server and JOSE dependencies. If using Spring Boot, you can configure the issuer and audience so Spring Boot creates the decoder:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
          audiences: https://api.example.com
~~~

`issuer-uri` allows Spring to discover the public key/JWK endpoint and verify the issuer. Resource Server verifies the signature and time claims such as `exp` and `nbf`; audience should be configured appropriately so that tokens are issued for the right resource server. If the system has custom claim rules, add a validator instead of decoding the JWT manually and trusting the payload.

`JwtAuthenticationConverter` converts a verified JWT into an `Authentication` with authorities. By default, Spring Security may map scopes to authorities with the `SCOPE_` prefix. If the system places roles in a custom claim such as `roles` or `authorities`, configure the converter accordingly so authorization uses the right authorities.

For opaque access tokens, do not use `JwtDecoder`. Validate them using an `OpaqueTokenIntrospector` or an `AuthenticationManager` configured to introspect tokens with the authorization server.

### Why authenticate only CONNECT?

A STOMP session has one user identity that Spring associates with subsequent messages. The interceptor only needs to read and validate the token on CONNECT, then call `setUser`. Subsequent SEND, SUBSCRIBE, or DISCONNECT messages in the session will carry the identity attached to that session.

Do not allow clients to send a `username`, `userId`, `role`, or `Principal` header to override the identity. Do not accept identity from the message payload. Fields like `from` or `sender` in a DTO, if needed for display, must be overwritten on the server with the authenticated `Principal`.

## 5. ChannelInterceptor ordering when using Spring Security

If the application uses both custom token authentication and Spring Security authorization, the authentication interceptor must run **before** the authorization interceptor. Spring Framework recommends placing the custom authentication configurer in a separate `WebSocketMessageBrokerConfigurer` class annotated with:

~~~java
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
~~~

In the previous section, `StompTokenAuthenticationConfig` is separated and given that order. Spring Security's authorization configuration is registered independently. Consequently, when the authorization interceptor runs, the user header already holds a valid Authentication.

If the authentication interceptor runs after authorization, Spring Security may see the CONNECT message without an authenticated user and reject the connection or evaluate permissions against an anonymous principal.

Do not register the same authentication interceptor multiple times across multiple configurers, as doing so can cause the token to be processed repeatedly and make troubleshooting difficult.

## 6. Authentication does not replace Authorization

Authentication answers the question “who is connecting?”. Authorization answers “what is that person allowed to do?”.

Calling `setUser(authentication)` only attaches the identity and authorities to the session. It does not automatically allow the user to send to every destination. Configure authorization for inbound messages, specifically distinguishing two STOMP command types:

- `MESSAGE`: the client sends data to the server or a destination.
- `SUBSCRIBE`: the client subscribes to receive messages from a destination.

Example modern Spring Security configuration with `@EnableWebSocketSecurity` and `AuthorizationManager`:

~~~java
import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class WebSocketAuthorizationConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/**").hasRole("USER")
            .simpSubscribeDestMatchers("/user/**").hasRole("USER")
            .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

The sample rules mean:

- Messages without a destination, including session control commands, require an authenticated user.
- Clients with role `USER` may send messages to application destinations `/app/**`.
- Clients with role `USER` may subscribe to `/user/**` destinations.
- Other MESSAGE or SUBSCRIBE frames are denied.
- Remaining messages are denied by default.

In particular, do not allow clients to send MESSAGE directly to `/topic/**` or `/queue/**` if these are broker destinations intended for server-emitted messages. Allowing that would let clients spoof system messages or inject messages into unauthorized queues. Similarly, do not let clients arbitrarily subscribe to `/queue/**` as that could expose another user's messages. Grant subscribe permissions for specific destinations.

Spring Security protects `clientInboundChannel`; the same authorization mechanism is not applied to `clientOutboundChannel`. Therefore, inbound subscriptions must be protected to control who can receive outbound messages.

## 7. CSRF and Same Origin when using tokens

Bearer tokens and CSRF solve two different problems:

- A Bearer token authenticates the client and identifies the user.
- A CSRF token helps protect STOMP CONNECT against unauthorized cross-origin connections in a browser model.

With `@EnableWebSocketSecurity`, Spring Security requires a CSRF token on inbound CONNECT by default. The client must send the CSRF token in the STOMP headers alongside Authorization when using token authentication at the STOMP layer.

Do not disable CSRF simply because you already have a JWT. If the application needs to customize CSRF for SockJS fallback, exclude only the specific HTTP transport endpoints needed and retain CSRF checking at STOMP CONNECT under the appropriate configuration. At the same time, configure explicit allowed origins for the WebSocket endpoint.

## 8. Token expiration and long-lived WebSocket sessions

Checking a token at CONNECT does not mean the token will automatically be re-verified on every frame. Spring attaches the Principal to the session and uses it for subsequent messages. Therefore, if a JWT expires while the WebSocket session remains open, the session may retain the authenticated identity until it is closed or additional checks occur.

Choose a clear policy:

- Use access tokens with lifetimes aligned with session lifetimes.
- When a token is refreshed, the client can reconnect using the new token.
- If immediate permission revocation is required, consider opaque token introspection, a denylist/revocation state, or proactively closing the relevant sessions.
- For systems requiring checks on continuously changing permissions, consider additional checks at the message or business layer.
- Do not assume changing a role in the authorization server will automatically update the authorities of an existing WebSocket session.

With self-contained JWTs, the server normally does not know a token was revoked before `exp` without an additional stateful mechanism. This is a trade-off to factor in when choosing JWTs for long-lived connections.

## 9. Common errors

### CONNECT is rejected even though the HTTP handshake succeeded

A successful HTTP handshake only proves the transport opened. If the server requires a Bearer token at STOMP CONNECT, the client must still send the native `Authorization` header. Check `connectHeaders`, header names, and the `Bearer` prefix.

### Token is valid, yet the user remains anonymous

Check whether the interceptor runs on `clientInboundChannel`, handles only CONNECT, calls `accessor.setUser(authentication)`, and is registered before the Spring Security interceptor. Ensure the converter returns an Authentication with the appropriate principal and authorities.

### Cannot read the Authorization header

Use `StompHeaderAccessor.getFirstNativeHeader(...)` to read the STOMP native header. Do not use HTTP servlet request headers to look for a token if the client sends the token in the CONNECT frame. Verify the exact header name sent by the client.

### JWT is decoded but not fully verified

Do not manually base64-decode a JWT and trust its claims. Use a `JwtDecoder` configured with JWK/issuer, signature, expiration, and audience verification. A token with a valid signature but the wrong audience must still not be accepted for the current application.

### User authenticates successfully but accesses unauthorized destinations

This is an authorization issue. Check the `AuthorizationManager` rules, authority mapping, and the distinction between MESSAGE and SUBSCRIBE. Do not allow clients to write directly to broker destinations or subscribe to internal queues outside their granted scope.

### CONNECT fails with a CSRF error

If using `@EnableWebSocketSecurity`, send the CSRF token with the exact header name and value in STOMP CONNECT. A Bearer token does not replace a CSRF token. With SockJS, follow the CSRF guidance for transport endpoints; do not disable CSRF globally.

### Token appears in logs

Do not log full STOMP headers or CONNECT frames in production. Redact Authorization, avoid passing tokens in URLs, use `wss://` to encrypt traffic in transit, and do not store tokens in telemetry or exception messages.

## 10. Testing token authentication

Test both the interceptor and the entire STOMP security chain:

1. CONNECT without Authorization is rejected.
2. Malformed Authorization or missing Bearer scheme is rejected.
3. JWT with an invalid signature, expired timestamp, not-yet-valid timestamp, or wrong issuer is rejected.
4. JWT whose audience is not intended for the application is rejected.
5. Valid JWT produces an Authentication with the right principal name and authorities.
6. Subsequent messages in the session carry the same user identity.
7. Clients cannot change users via a username header or payload field.
8. Users lacking the required role cannot send to `/app/**` or subscribe to `/user/**`.
9. Clients cannot send MESSAGE directly to `/topic/**` or `/queue/**`.
10. CONNECT missing a CSRF token is rejected when Spring Security requires it.
11. Token expiration during a long-lived session is handled according to the chosen reconnect/reauthentication policy.
12. The Authorization header is not logged and is not forwarded unnecessarily.

Unit tests can mock `JwtDecoder` and the converter to verify the interceptor. Integration tests should start the WebSocket/STOMP endpoint and send real CONNECT frames to verify interceptor ordering, CSRF, and authorization work properly.

## 11. Implementation principles

- Prefer HTTP handshake authentication if the application already has sessions/cookies or clients support custom handshake headers.
- Use STOMP CONNECT tokens only when there is a practical reason, such as browser clients unable to send custom HTTP headers.
- Authenticate tokens only on CONNECT and attach the user via `accessor.setUser(authentication)`.
- Use a configured `JwtDecoder` or introspection; do not manually decode and trust JWT payloads.
- Verify issuer, audience, signature, expiration, and mandatory claims.
- Keep the authentication interceptor separate from the authorization configuration.
- Place the authentication interceptor before the Spring Security interceptor as guided by Spring.
- Maintain CSRF and allowed-origin protection; a CSRF token is distinct from a Bearer token.
- Authorize by destination and command; protecting SUBSCRIBE is just as important as MESSAGE.
- Never trust usernames, roles, or senders supplied by the client in headers/payloads.
- Never log tokens; use TLS/WSS exclusively.
- Have a policy for tokens that expire or are revoked while a session remains open.

## References

- [Spring Framework Reference — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Spring Framework Reference — Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework Reference — Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html)
- [Spring Security Reference — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
