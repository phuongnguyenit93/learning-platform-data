# User Identity from HTTP Handshake to STOMP Session in Spring

## Objective

A STOMP over WebSocket connection begins with an HTTP request. Spring can obtain the authenticated identity from that HTTP request, attach the identity to the WebSocket session, and then propagate that identity into subsequent STOMP messages. Therefore, controllers can receive a Principal parameter without requiring the client to send the username in the payload.

There are two common authentication models:

- **Authentication at the HTTP handshake**: suitable when the application already uses Spring Security with cookies/sessions or an HTTP authentication mechanism.
- **Authentication at STOMP CONNECT**: suitable when the client sends a bearer token in STOMP CONNECT headers, for example in an SPA or mobile application that does not use an HTTP session.

Both models must produce a trustworthy Principal on the server side. The difference lies in the timing and the authentication layer. A self-declared username field sent by the client must never be treated as an authenticated identity.

## 1. Lifecycle from HTTP handshake to STOMP message

With standard WebSocket, the client first sends an HTTP request containing an Upgrade header. If the server accepts, the connection switches to the WebSocket protocol. STOMP then runs as a sub-protocol over this connection.

With SockJS fallback, Spring may use a sequence of HTTP transport requests instead of pure WebSocket, but the identity model remains bound to the SockJS/WebSocket session.

Overall flow:

~~~text
Browser / Mobile client
        |
        | HTTP request: GET /ws
        | Cookie / HTTP authentication
        v
Spring Security filter chain
        |
        | authenticate request, create SecurityContext
        v
WebSocket handshake / SockJS transport
        |
        | HttpServletRequest.getUserPrincipal()
        v
WebSocket session bound to Principal
        |
        | STOMP CONNECT
        | STOMP SEND / SUBSCRIBE / DISCONNECT
        v
Spring clientInboundChannel
        |
        | message with simpUser / Principal
        v
@MessageMapping, ChannelInterceptor, AuthorizationManager
~~~

With the HTTP session model, Spring automatically transfers the Principal of the HTTP request to the WebSocket session. Subsequent STOMP messages carry the corresponding user information. Applications normally do not need to manually copy the username from HTTP to the STOMP payload.

With the token-at-STOMP-CONNECT model, the HTTP handshake may not yet have an authenticated user. A ChannelInterceptor validates the token on the CONNECT frame and calls setUser(...) so that Spring remembers the user for subsequent messages on the same session.

## 2. Default model: HTTP authentication before the handshake

This is the natural choice when the application already uses Spring Security to protect HTTP:

1. The user logs in via form login, HTTP Basic, OAuth2 Login, or another HTTP authentication mechanism.
2. Spring Security authenticates the request and stores the Authentication in the SecurityContext. With a cookie-based session, the SecurityContext is associated with the HTTP session.
3. The browser sends a request to open a WebSocket to the endpoint, for example /ws, along with the appropriate session cookie.
4. Spring reads the Principal from the HTTP request during the handshake.
5. The WebSocket session is created with that same identity.
6. Every STOMP message from the session is tagged with the corresponding user information.

Endpoint configuration example:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

If the HTTP request to /ws has already been authenticated by Spring Security, Spring WebSocket can use that request's Principal. There is no need to add a username to the CONNECT frame to repeat the already-authenticated identity.

### Why are CONNECT login/passcode not used by default?

STOMP defines login and passcode headers on the CONNECT frame, which are useful for STOMP over TCP. However, with STOMP over WebSocket in Spring, by default Spring does not use these headers to authenticate the user. Spring assumes the identity has already been authenticated at the HTTP layer and attached to the WebSocket/SockJS session.

This avoids having two independent authentication mechanisms coexist without a unified rule. If you want to use a token or credentials at STOMP CONNECT, the application must authenticate them itself using a ChannelInterceptor and set the Principal on the message.

## 3. Reading the Principal in controllers and messages

A @MessageMapping method can receive the Principal directly:

~~~java
public record ChatCommand(String text) {}

public record ChatMessage(String sender, String text) {}

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(
            @Payload ChatCommand command,
            Principal principal) {

        return new ChatMessage(principal.getName(), command.text());
    }
}
~~~

This is an illustrative controller snippet. The application needs to declare DTOs, configure message converters, and ensure the endpoint requires authentication before the method is invoked.

With the application destination prefix /app, the client sends SEND to /app/chat.send; Spring routes it to @MessageMapping("/chat.send"). The Principal reflects the identity bound to the session. The server populates the sender field from the Principal, not from a sender value sent by the client.

You can read the identity in an interceptor using StompHeaderAccessor or SimpMessageHeaderAccessor:

~~~java
public class UserAuditInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);
        Principal user = accessor.getUser();

        if (user != null) {
            String username = user.getName();
            // Log audit event according to the application's policy.
        }

        return message;
    }
}
~~~

In Spring Messaging message headers, the user usually appears under the simpUser header. Using accessor.getUser() or a Principal parameter avoids depending on internal header names.

Do not write access tokens, session cookies, or secrets into audit logs. If you need to record the sender, log only the authenticated subject/user ID along with the necessary metadata.

## 4. Customizing the identity directly at the HTTP handshake

In some applications, the HTTP request has been authenticated by a custom mechanism or a special Principal needs to be attached to the WebSocket session. Spring allows customizing HandshakeHandler, for example by overriding determineUser(...).

~~~java
public class CustomHandshakeHandler extends DefaultHandshakeHandler {

    @Override
    protected Principal determineUser(
            ServerHttpRequest request,
            WebSocketHandler wsHandler,
            Map<String, Object> attributes) {

        return request.getPrincipal();
    }
}
~~~

This snippet illustrates the extension point and returns the Principal provided by the HTTP layer. In a real application, create a new Principal only after verifying the identity from a trusted source. If Spring Security authorization relies on Authentication, the custom Principal must also be an appropriate Authentication; an object that only implements Principal may not supply authorities to the SecurityContext.

You can attach the HandshakeHandler to the endpoint:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setHandshakeHandler(new CustomHandshakeHandler());
}
~~~

If Spring Security already produces the correct Authentication and request Principal, there is no need to customize HandshakeHandler. Only add a custom handler when there is a genuine requirement for how the Principal is determined at handshake time.

You should distinguish HandshakeInterceptor from HandshakeHandler:

- HandshakeInterceptor runs before and after the handshake, typically used to inspect the request or pass metadata into the WebSocket session attributes.
- HandshakeHandler governs the handshake itself and has the determineUser(...) extension point to determine the WebSocket session's Principal.
- Metadata in attributes does not automatically become an Authentication. A value in attributes is only trustworthy when the server has verified it.

## 5. When should you authenticate at STOMP CONNECT?

Some clients do not use a cookie-based HTTP session:

- SPA applications using JWT access tokens.
- Mobile applications sending bearer tokens.
- Internal services using client credentials.
- Stateless applications that do not maintain a server-side HTTP session.

The WebSocket API in browsers does not allow JavaScript to arbitrarily set custom HTTP headers for initiating a WebSocket connection. The SockJS JavaScript client also does not support custom HTTP headers for transport requests. Therefore, when cookies are not used, the common approach is to send the token in STOMP CONNECT headers and authenticate on the server using a ChannelInterceptor.

Client-side example with a STOMP library:

~~~javascript
const client = new Client({
    brokerURL: "wss://example.com/ws",
    connectHeaders: {
        Authorization: "Bearer " + accessToken
    },
    onConnect: () => {
        client.subscribe("/user/queue/private", frame => {
            console.log(frame.body);
        });
    }
});

client.activate();
~~~

In the example, connectHeaders are headers of the STOMP CONNECT frame. They are not the HTTP Authorization header of the WebSocket handshake. For browsers, this is an important distinction: JavaScript cannot add arbitrary headers to the HTTP Upgrade request, but the STOMP client can add application headers to the CONNECT frame after the WebSocket is opened.

Do not put a bearer token into the query string if another option exists. URLs can be recorded in access logs, reverse proxy logs, monitoring, analytics, or browser history. If a query parameter must be used for a constrained environment, the token must have a very short lifetime, narrow scope, and must not be logged; prefer a safer design.

## 6. Authenticating tokens with a ChannelInterceptor

Spring allows registering a ChannelInterceptor on clientInboundChannel. The interceptor inspects the CONNECT frame, validates the token, and attaches the Authentication to the message using accessor.setUser(...). Spring saves that user and associates it with subsequent STOMP messages in the same session.

Example with Spring Security's JwtDecoder and JwtAuthenticationConverter:

~~~java
@Configuration
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
public class StompTokenAuthenticationConfig
        implements WebSocketMessageBrokerConfigurer {

    private final JwtDecoder jwtDecoder;
    private final JwtAuthenticationConverter jwtAuthenticationConverter;

    public StompTokenAuthenticationConfig(
            JwtDecoder jwtDecoder,
            JwtAuthenticationConverter jwtAuthenticationConverter) {
        this.jwtDecoder = jwtDecoder;
        this.jwtAuthenticationConverter = jwtAuthenticationConverter;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new ChannelInterceptor() {

            @Override
            public Message<?> preSend(Message<?> message, MessageChannel channel) {
                StompHeaderAccessor accessor =
                        MessageHeaderAccessor.getAccessor(
                                message, StompHeaderAccessor.class);

                if (accessor != null
                        && StompCommand.CONNECT.equals(accessor.getCommand())) {

                    String authorization =
                            accessor.getFirstNativeHeader("Authorization");

                    if (authorization == null
                            || !authorization.startsWith("Bearer ")) {
                        throw new BadCredentialsException("Missing bearer token");
                    }

                    String token = authorization.substring(7);
                    Jwt jwt = jwtDecoder.decode(token);
                    Authentication authentication =
                            jwtAuthenticationConverter.convert(jwt);

                    if (authentication == null) {
                        throw new BadCredentialsException("Invalid bearer token");
                    }

                    accessor.setUser(authentication);
                }

                return message;
            }
        });
    }
}
~~~

This is an illustrative configuration excerpt; imports and the JwtDecoder/JwtAuthenticationConverter beans are omitted. The application needs the corresponding Spring Security OAuth2 Resource Server/Jose dependencies and must configure the decoder with a trusted issuer or public key. The validator configuration must check required claims such as issuer, audience, and expiration. The converter can map scopes/roles into authorities used by Spring Security authorization.

Key responsibilities in the interceptor:

1. Authenticate only the CONNECT frame to establish the identity for the session.
2. Extract the token from the native STOMP header sent by the client.
3. Verify the signature, issuer, audience, expiration, and required claims through the decoder/validator.
4. Create an Authentication from the verification result, including authorities if the application needs authorization.
5. Call accessor.setUser(authentication) to attach the trusted Principal to the CONNECT message.
6. Reject CONNECT with an exception if the token is missing, malformed, expired, or invalid.

The example using JwtAuthenticationConverter is one way to implement this. Another Authentication type or custom authentication mechanism may be used, as long as the object attached via setUser(...) is the result of server-side authentication and carries the required authorities.

### Interceptor ordering

When using Spring Security to authorize STOMP messages, the token authentication interceptor must run before Spring Security's security interceptor so that the SecurityContext can read the authenticated user.

The Spring documentation recommends declaring a separate custom WebSocketMessageBrokerConfigurer and annotating it with @Order(Ordered.HIGHEST_PRECEDENCE + 99). You should not simply add the interceptor arbitrarily to another configuration and assume the execution order.

If token authentication does not run first, Spring Security may evaluate CONNECT or subsequent messages as an anonymous user, resulting in access denial even with a valid token.

## 7. Integrating Spring Security: CSRF and authorization

Authentication and authorization are two distinct concerns:

- **Authentication** answers who the user is.
- **Authorization** decides which messages the user is allowed to send or receive.

You can enable STOMP protection with @EnableWebSocketSecurity and declare an AuthorizationManager<Message<?>>. The example below illustrates how to authorize inbound messages:

~~~java
@Configuration
@EnableWebSocketSecurity
public class WebSocketSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/**").hasRole("USER")
            .simpSubscribeDestMatchers("/user/**", "/topic/public")
                .hasRole("USER")
            .simpTypeMatchers(SimpMessageType.MESSAGE).denyAll()
            .simpTypeMatchers(SimpMessageType.SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

This is a basic policy example and needs to be adjusted to match your application's actual destinations and roles. You must consider SEND, SUBSCRIBE, CONNECT, DISCONNECT, and internal messages; do not copy it verbatim if the application has different requirements.

### CSRF on STOMP CONNECT

When Spring Security WebSocket support is enabled, inbound CONNECT requires a valid CSRF token by default. This mechanism helps prevent unauthorized WebSocket connections from other origins by requiring the client to possess a valid CSRF token.

With SockJS, because the transport does not allow sending arbitrary HTTP headers, the CSRF token is typically sent in STOMP CONNECT headers. The client must retrieve the token from the application's CSRF mechanism and add the corresponding header to connectHeaders.

~~~javascript
const connectHeaders = {
    Authorization: "Bearer " + accessToken,
    [csrfHeaderName]: csrfToken
};

const client = new Client({
    brokerURL: "wss://example.com/ws",
    connectHeaders
});
~~~

The header name and token must match the values issued by Spring Security for the current request. If the application uses an HTTP session, cookies still need to be sent according to browser policy and matching same-origin rules.

Do not disable CSRF globally just to make STOMP CONNECT work. If you need to configure an exception in the HTTP filter chain for the handshake endpoint, scope it strictly to the exact URL needed and keep CSRF protection at the STOMP CONNECT layer according to the chosen security configuration.

### Authorizing SEND and SUBSCRIBE separately

For example, a client may be allowed to SUBSCRIBE to /topic/system/notifications but not allowed to SEND to that destination. If a client is allowed to send messages directly to a destination that broadcasts system notifications, the client could spoof notifications.

A common policy:

- Allow authenticated users to SEND to /app/**.
- Allow authorized users to SUBSCRIBE to /user/** and specific public topics.
- Deny MESSAGE from clients to /topic/** and /queue/** unless direct publishing is explicitly required.
- Do not allow clients to SUBSCRIBE to internal physical queues resolved by Spring for other users.
- Check business-level permissions in controllers/services, even after a message passes the authorization matcher.

## 8. Principal, username, and client-supplied data

A common mistake is accepting a username from the payload:

~~~java
public record ChatCommand(String from, String text) {}
~~~

And then using the from field directly to identify the sender. This approach allows a client to impersonate another user.

Instead:

~~~java
@MessageMapping("/chat.send")
public void send(@Payload ChatCommand command, Principal principal) {
    String authenticatedUsername = principal.getName();

    chatService.send(authenticatedUsername, command.text());
}
~~~

The client sends only the business content. The server determines the sender from the Principal. If a message needs to be sent to a specific recipient, the client can send the recipient ID, but the service must verify that the current user has permission to send to that recipient.

You should also not trust a native STOMP header named user sent by the client. A client can put arbitrary headers into a CONNECT or SEND frame. The identity must come from the HTTP SecurityContext or from server-side token validation, and then be attached via setUser(...).

## 9. Session lifecycle, token expiration, and reconnect

The identity bound to a WebSocket/STOMP session has its own lifecycle:

- The HTTP handshake creates the WebSocket session and attaches the Principal.
- STOMP CONNECT initializes the messaging session.
- SEND and SUBSCRIBE use the identity bound to the session.
- DISCONNECT or closing the transport terminates the session.
- Reconnecting creates a new WebSocket/SockJS session and must re-authenticate according to policy.

With a JWT validated at CONNECT, Spring does not automatically invoke JwtDecoder again for every SEND or SUBSCRIBE. The token is typically checked at connection time. Because WebSocket is a long-lived connection, you need to decide how to handle a token that expires or is revoked while the socket remains open.

Strategies to consider:

1. Limit the maximum lifetime of the WebSocket session based on the token lifetime.
2. Proactively close the session when the token expires or the user's permissions are revoked.
3. Require the client to reconnect and authenticate with a new access token.
4. Perform business-level permission checks on each message for sensitive operations.
5. Use a session registry or centralized revocation mechanism if the system needs to invalidate connections immediately.

Do not assume that refreshing a token automatically updates the Principal of an existing STOMP session. When a new token is issued, the application needs a clearly designed and controlled reconnect flow or identity-update mechanism.

When handling SessionDisconnectEvent, cleanup logic should be idempotent because a single session can emit multiple disconnect signals in certain connection-closing scenarios. Do not let repeated disconnect handling delete data or release resources multiple times.

## 10. Multiple tabs, multiple devices, and session identifiers

A user may open multiple tabs or connect from multiple devices. Those sessions may share the same Principal while still having separate session IDs.

This affects:

- Sending messages to all sessions of a user.
- Sending messages only to the session that originated the request.
- Tracking online presence.
- Cleaning up sessions after disconnect.
- Broadcasting notifications when one device logs out.
- Enforcing concurrent connection limits.

Do not use the username as the session ID. The username identifies the user; the session ID identifies a specific connection. If you need to send specifically to a single tab, use Spring's destination/session mechanism or a business-layer correlation ID; do not manually construct physical queues by concatenating the username with an arbitrary string.

When running multiple instances, each node may manage different WebSocket sessions. The user registry and broker relay must be configured appropriately if you want to route user destinations across nodes. One node knowing a Principal does not mean another node automatically knows all sessions for that user.

## 11. Testing identity from handshake to controller

You should test each boundary rather than only verifying that the WebSocket opens successfully:

1. **HTTP authentication**: an unauthenticated handshake request must be rejected if the endpoint requires login.
2. **Principal propagation**: an authenticated handshake creates a session with the right Principal.
3. **STOMP CONNECT**: the session is allowed to CONNECT and has the appropriate user header.
4. **Token authentication**: missing, invalidly signed, wrong issuer/audience, or expired tokens must be rejected.
5. **Interceptor order**: Spring Security sees the attached Authentication before authorization runs.
6. **Controller identity**: the Principal parameter in @MessageMapping matches the logged-in user.
7. **Spoofing**: client-supplied payloads or native headers cannot alter the authenticated identity.
8. **CSRF/Origin**: CONNECT missing a CSRF token or requests from disallowed origins must be handled according to policy.
9. **Reconnect**: a new session must re-authenticate; an expired token must not inadvertently retain permissions longer than policy allows.
10. **Disconnect**: cleanup is safe when disconnect events arrive multiple times.

You can use WebSocketStompClient with WebSocketClient or SockJsClient depending on the transport. For integration tests, exercise the full flow of HTTP handshake, STOMP CONNECT, SEND, and SUBSCRIBE under the real security configuration to catch issues with sessions, CSRF, and interceptor ordering.

## 12. Common errors and troubleshooting

**Principal in @MessageMapping is null**

- Check whether the HTTP handshake request was authenticated.
- Check whether the cookie/session is being sent to the right host, scheme, and path.
- If using a token at STOMP CONNECT, check whether the ChannelInterceptor runs on CONNECT and calls accessor.setUser(...).
- Check whether the interceptor is registered on the wrong channel or in the wrong order.

**Authorization header is present in CONNECT, yet Spring still treats the user as anonymous**

- Spring does not authenticate STOMP login/passcode for WebSocket by default.
- You must validate the bearer token yourself using a ChannelInterceptor.
- Attach the Authentication via setUser(...) before Spring Security authorization runs.
- Ensure the interceptor is registered with the appropriate ordering.

**Token is valid, yet CONNECT is rejected by Spring Security**

- Check the CSRF token in the STOMP CONNECT headers when @EnableWebSocketSecurity is enabled.
- Check that the token authentication interceptor runs before Spring Security.
- Check whether the authorization matcher permits CONNECT and the destinations being used.

**Client can spoof the sender**

- Do not use a from, username, or userId field in the payload as the Principal.
- Do not trust client-supplied native STOMP headers.
- Obtain the identity from the request Principal or an Authentication verified by the server.

**Browser cannot send a custom Authorization HTTP header**

- The browser WebSocket API does not allow setting arbitrary HTTP handshake headers.
- Use cookies/sessions if appropriate, or send a bearer token in STOMP CONNECT headers and validate it with a ChannelInterceptor.
- Avoid putting tokens in query strings because URLs may be logged.

**A connection keeps working after the token expires**

- CONNECT authentication does not automatically re-check the token on every frame.
- Design a session lifetime, close connections on expiration, or require reconnection.
- Check business-level permissions for sensitive operations and have a session revocation mechanism when needed.

**Disconnect event triggers cleanup multiple times**

- Design the handler to be idempotent.
- Use the session ID and closed state to ensure a session is cleaned up only once at the business level.

## 13. Choosing an authentication model

| Context | Preferred model |
|---|---|
| Web application already using Spring Security and cookie sessions | Authenticate the HTTP handshake, use the Principal propagated by Spring to WebSocket |
| SPA/mobile application using JWT without an HTTP session | Token in STOMP CONNECT + ChannelInterceptor |
| Java STOMP client that can send custom HTTP headers | Can authenticate at the HTTP handshake via HTTP headers or use a CONNECT token |
| Need a custom Principal right when creating the WebSocket session | Custom HandshakeHandler / determineUser after verifying identity |
| Need SEND/SUBSCRIBE authorization | Spring Security WebSocket authorization on inbound messages |
| Using @EnableWebSocketSecurity | Ensure a CSRF token is sent in CONNECT per the default configuration |
| Need to revoke a user or token while the socket is open | Session registry, timeout, closing the session, or per-message permission checks |

You can remember the chain of responsibility as follows: HTTP Security or the CONNECT interceptor authenticates the user; Spring attaches the Principal to the session; controllers and message interceptors read the Principal; Spring Security authorization decides which actions are permitted. Each step has its own responsibility and must be configured around the same trusted identity.

## References

- Spring Framework — Authentication: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html
- Spring Framework — Token Authentication: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html
- Spring Framework — Interception: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html
- Spring Framework — Authorization: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html
- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- Spring Framework — WebSocket API and handshake: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
