# HandshakeInterceptor, Session Attributes, and Principal

> Goal: understand the lifecycle of the HTTP WebSocket handshake, use `HandshakeInterceptor` to inspect the request and pass data into the `WebSocketSession`, distinguish handshake attributes from HTTP session attributes and the `Principal`, and protect user identity in WebSocket/STOMP.

## 1. WebSocket Starts with an HTTP Handshake

An ordinary WebSocket connection starts with an HTTP request that asks for a protocol upgrade (`Upgrade: websocket`). The server checks the request, negotiates the protocol if any, and switches the connection to WebSocket. After a successful handshake, the client and server exchange frames in both directions over the same long-lived connection.

Spring WebSocket provides two main processing layers:

- `HandshakeInterceptor`: runs around the HTTP handshake step; it can inspect the request, reject the connection, or prepare attributes for the session.
- `WebSocketHandler`: handles the connection lifecycle and frames after a successful handshake, for example `afterConnectionEstablished`, `handleTextMessage`, and `afterConnectionClosed`.

If you use STOMP over WebSocket, Spring also has a messaging endpoint, channels, and `ChannelInterceptor` to handle STOMP frames such as `CONNECT`, `SUBSCRIBE`, and `SEND`. `HandshakeInterceptor` and `ChannelInterceptor` belong to two different stages.

Basic flow:

```text
Browser / WebSocket client
          |
          | HTTP Upgrade request
          v
   HandshakeInterceptor
       beforeHandshake()
          |
          v
   HandshakeHandler / server
          |
           | Upgrade succeeds
          v
      WebSocketSession
       /           \
      v             v
 WebSocketHandler  STOMP messaging
      |             |
      v             v
  WebSocket frame  ChannelInterceptor
                     and @MessageMapping
```

## 2. What Is HandshakeInterceptor?

`org.springframework.web.socket.server.HandshakeInterceptor` is an interface that lets you intervene before and after Spring processes the WebSocket handshake. The interface has two methods:

```java
boolean beforeHandshake(
        ServerHttpRequest request,
        ServerHttpResponse response,
        WebSocketHandler wsHandler,
        Map<String, Object> attributes
) throws Exception;

void afterHandshake(
        ServerHttpRequest request,
        ServerHttpResponse response,
        WebSocketHandler wsHandler,
        Exception exception
);
```

`beforeHandshake` is called before the handshake is processed:

- Returning `true`: allows the handshake process to continue.
- Returning `false`: rejects the handshake.
- It can write data into `attributes`; Spring copies these values into the attributes of the `WebSocketSession` that is created.
- It can throw an exception if the check encounters an error that needs to stop the handshake.

`afterHandshake` is called after the handshake process ends. The `exception` parameter indicates an exception that arose during the process; a `null` value means no exception was passed to the callback. This is the callback for the end of the handshake, not the callback for when the WebSocket session closes.

## 3. Implementing a Custom HandshakeInterceptor

The following example requires the request to be authenticated, receives a tenant ID from a header, and checks whether the user has permission to access that tenant. Only after the check succeeds does the interceptor put the tenant ID into the handshake attributes.

```java
import java.security.Principal;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

@Component
class TenantHandshakeInterceptor implements HandshakeInterceptor {

    private final TenantAccessService tenantAccessService;

    TenantHandshakeInterceptor(TenantAccessService tenantAccessService) {
        this.tenantAccessService = tenantAccessService;
    }

    @Override
    public boolean beforeHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Map<String, Object> attributes) {

        Principal principal = request.getPrincipal();
        if (principal == null) {
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return false;
        }

        String tenantId = request.getHeaders().getFirst("X-Tenant-ID");
        if (tenantId == null || tenantId.isBlank()
                || !tenantAccessService.canAccess(principal.getName(), tenantId)) {
            response.setStatusCode(HttpStatus.FORBIDDEN);
            return false;
        }

        attributes.put("tenantId", tenantId);
        return true;
    }

    @Override
    public void afterHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Exception exception) {
        if (exception != null) {
            // Log the handshake failure; do not log tokens or sensitive data.
        }
    }
}
```

`TenantAccessService` is a business service provided by the application. The `X-Tenant-ID` header is sent by the client and is therefore still untrusted data; the service must verify that the current user has permission to access the requested tenant. Do not use the header value alone to grant access.

Example of registering the interceptor:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
class WebSocketConfig implements WebSocketConfigurer {

    private final WebSocketHandler chatHandler;
    private final TenantHandshakeInterceptor tenantInterceptor;

    WebSocketConfig(
            WebSocketHandler chatHandler,
            TenantHandshakeInterceptor tenantInterceptor) {
        this.chatHandler = chatHandler;
        this.tenantInterceptor = tenantInterceptor;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(chatHandler, "/ws/chat")
                .addInterceptors(tenantInterceptor)
                .setAllowedOrigins("https://app.example.com");
    }
}
```

This is a raw WebSocket configuration using `@EnableWebSocket`. The application needs to provide the `chatHandler` bean. The list of allowed origins should be the frontend's actual origins. If you use STOMP, configure the endpoint through `@EnableWebSocketMessageBroker` and `StompEndpointRegistry`, and then register the interceptor on the corresponding endpoint.

## 4. Handshake Attributes and WebSocketSession

The `attributes` parameter in `beforeHandshake` is where you put server-verified data into the WebSocket session. Spring copies this map when it creates the session. After the handshake, the handler reads the data using `WebSocketSession.getAttributes()`.

Example:

```java
import java.security.Principal;

import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

class ChatHandler extends TextWebSocketHandler {

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        Principal principal = session.getPrincipal();
        String tenantId = (String) session.getAttributes().get("tenantId");

        String username = principal != null ? principal.getName() : "anonymous";
        System.out.println("Connected user=" + username + ", tenant=" + tenantId);
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session,
            org.springframework.web.socket.CloseStatus status) {
        // Release the resources tied to the session here if needed.
    }
}
```

The code illustrates how to read two different sources of information: `getPrincipal()` returns the authenticated identity if any; `getAttributes()` returns the application data attached to the session during the handshake. `System.out.println` is only for illustration; a real application should use a structured logger.

Attributes are usually suitable for small data that is stable throughout the connection lifecycle, such as `tenantId`, locale, a workspace code, or a feature context that has been verified. Do not store the entire request, a servlet session object, secret tokens, large objects, or shared mutable state in this map.

## 5. HttpSessionHandshakeInterceptor

Spring provides `HttpSessionHandshakeInterceptor` to copy some or all of the attributes from the HTTP session into the handshake attributes. Those values can then be read through `WebSocketSession.getAttributes()`.

Two common ways to initialize it:

```java
import java.util.List;

import org.springframework.web.socket.server.support.HttpSessionHandshakeInterceptor;

// Default constructor: copies all HTTP session attributes and the session ID.
var copyEverything = new HttpSessionHandshakeInterceptor();

// Constructor with a list: copies only the specified attributes.
var copySelected = new HttpSessionHandshakeInterceptor(
        List.of("locale", "preferredTheme")
);
copySelected.setCopyHttpSessionId(false);
```

The default constructor copies all HTTP session attributes and the HTTP session ID. The constructor that takes a collection copies only the specified attributes; by default it still copies the HTTP session ID. You can turn off copying the ID with `setCopyHttpSessionId(false)`. `setCreateSession(false)` is the default, meaning the interceptor does not ask to create a new HTTP session just to read data.

Example of registering an interceptor with an allowlist:

```java
registry.addHandler(chatHandler, "/ws/chat")
        .addInterceptors(copySelected);
```

Choose the necessary attributes instead of copying the whole session. An HTTP session usually contains authentication information, CSRF state, user data, or internal objects. Copying everything increases the data that lives in the WebSocket session and can expose information if the handler logs or returns data incorrectly.

## 6. Distinguishing HTTP Session, WebSocket Session Attributes, and Principal

These three concepts are related but serve different purposes:

| Component | Content | How to access |
|---|---|---|
| HTTP session | Server-side state tied to HTTP requests through a cookie/session ID | `HttpSession` in a Servlet application |
| WebSocket session attributes | Application data attached to a WebSocket connection during the handshake | `WebSocketSession.getAttributes()` |
| `Principal` | The authenticated user identity | `request.getPrincipal()`, `WebSocketSession.getPrincipal()`, or the `Principal` parameter in a STOMP controller |

`HttpSessionHandshakeInterceptor` only copies the selected attributes from the HTTP session into the WebSocket session attributes. It does not turn those values into a `Principal` and does not perform user authentication.

With an ordinary Spring Security application, the handshake HTTP request has already been authenticated before the protocol upgrade. Spring automatically associates the HTTP request's `Principal` with the WebSocket/SockJS session. When using STOMP, that identity continues to be attached to messages as the user header.

Therefore, use the `Principal` as the source of the authenticated identity. Use handshake attributes for application context such as tenant or locale after it has been verified. Whether a user can access a particular destination or operation still requires authorization.

## 7. Principal in a Raw WebSocket Handler

With the raw WebSocket API, a handler can read the identity through `WebSocketSession.getPrincipal()`: 

```java
import java.security.Principal;

import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

class PrivateChatHandler extends TextWebSocketHandler {

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        Principal principal = session.getPrincipal();
        if (principal == null) {
            // Only allow anonymous if the application policy permits it.
            return;
        }

        registerConnection(principal.getName(), session.getId());
    }
}
```

`Principal` can be `null` if the request has not been authenticated. If the endpoint is only for logged-in users, protect the handshake with Spring Security or reject the connection in an interceptor. Do not take a username sent by the client in the query string or message body as the identity in place of the `Principal`.

## 8. Principal in STOMP and @MessageMapping

When using STOMP over WebSocket, Spring automatically passes the authenticated `Principal` from the HTTP handshake into the WebSocket/SockJS session and the subsequent messages. A controller can receive the `Principal` directly:

```java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
class ChatController {

    private final ChatService chatService;

    ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    @MessageMapping("/chat.send")
    public void send(ChatMessage message, Principal principal) {
        chatService.sendFrom(principal.getName(), message);
    }
}
```

The example assumes the endpoint already requires authentication and `principal` is not null. `ChatMessage` is an application DTO; `ChatService` is responsible for checking permission to send, storing the content, and routing the message. Do not rely only on the fact that a client can send to `/app/chat.send` to conclude that the person is allowed to send into any chat room.

By default, Spring ignores the STOMP `login` and `passcode` headers on the `CONNECT` frame when STOMP runs over WebSocket. Spring expects the identity to have already been authenticated at the HTTP transport. Those two headers still have meaning in some STOMP over TCP models, but you should not treat them as the default login mechanism for STOMP over WebSocket.

## 9. Token Authentication in STOMP CONNECT

Some applications do not use cookies or an HTTP session, for example a mobile app or a stateless system using JWT. In that case, you can send the token in a native header of the STOMP `CONNECT` and authenticate with a `ChannelInterceptor`.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompTokenAuthenticationConfig implements WebSocketMessageBrokerConfigurer {

    private final TokenAuthenticationService tokenAuthenticationService;

    StompTokenAuthenticationConfig(TokenAuthenticationService service) {
        this.tokenAuthenticationService = service;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(Message<?> message, MessageChannel channel) {
                StompHeaderAccessor accessor = MessageHeaderAccessor.getAccessor(
                        message, StompHeaderAccessor.class);

                if (accessor != null && StompCommand.CONNECT.equals(accessor.getCommand())) {
                    String token = accessor.getFirstNativeHeader("Authorization");
                    var authentication = tokenAuthenticationService.authenticate(token);
                    accessor.setUser(authentication);
                }
                return message;
            }
        });
    }
}
```

`TokenAuthenticationService` is a service implemented by the application to verify the token's signature, issuer, audience, expiration, and permissions and then return a valid `Authentication`. When the token is invalid, the service needs to throw an authentication exception to reject the `CONNECT` frame. After calling `accessor.setUser(authentication)`, Spring stores the user for the STOMP session and attaches that identity to subsequent messages.

Browsers do not let the JavaScript WebSocket API freely add HTTP headers to the handshake. If you use cookies/a session, rely on HTTP authentication. If you need a stateless token for the browser, the STOMP CONNECT native header may be more suitable; avoid putting a token in the query string because the URL can appear in access logs, proxy logs, history, or monitoring systems.

If Spring Security protects the message channel, the interceptor that authenticates CONNECT must run before Spring Security's authorization interceptor so that the user is attached before permissions are checked. Separate the authentication interceptor configuration and set the order following the guidance of the Spring Security version in use.

## 10. HandshakeInterceptor and ChannelInterceptor Differ

| Criterion | `HandshakeInterceptor` | `ChannelInterceptor` |
|---|---|---|
| When | Before/after the HTTP WebSocket handshake | Before/after a message passes through a Spring messaging channel |
| Subject | `ServerHttpRequest`, `ServerHttpResponse`, `WebSocketHandler`, handshake attributes | `Message<?>`, `MessageChannel`, STOMP headers/accessor |
| Typical tasks | Check the request, reject the connection, add tenant/locale/session context | Authenticate STOMP CONNECT, authorization, logging, or checking SEND/SUBSCRIBE |
| Scope | Once when the connection/transport handshake is created | Many messages during the STOMP session lifecycle |
| Example | Block a user who is not logged in or an invalid tenant | Check the token in CONNECT, block subscribing to an unauthorized destination |

Do not use `HandshakeInterceptor` to check each STOMP message because the interceptor only runs at the handshake stage. Conversely, `ChannelInterceptor` does not replace authenticating the HTTP handshake and checking the origin.

## 11. Origin, CSRF, and Authorization

A handshake interceptor can reject a request, but WebSocket security needs multiple layers:

- **Authentication:** identify the user through HTTP Security or token authentication in STOMP CONNECT.
- **Origin validation:** restrict the origins allowed to connect to reduce the risk of a website outside the domain opening a connection using the user's cookie. Configure allowed origins on the endpoint and consider the proxy/load balancer.
- **Authorization:** check whether the user has permission to send to a destination, subscribe to a topic, or operate on a specific resource. With STOMP, Spring Security provides message authorization based on the user header.
- **CSRF:** when using cookie-based authentication, configure Spring Security WebSocket/STOMP according to the application's CSRF policy; do not disable the protection just to make CONNECT work.
- **Tenant isolation:** the tenant ID must be matched against the `Principal` on the server; do not trust a tenant value the client declares itself.

Origin is not a user identity. A request with a valid origin still needs authentication and authorization. Likewise, having a `Principal` does not mean the user is permitted to subscribe to every destination.

## 12. Session Lifecycle and Cleanup

You need to distinguish the handshake callbacks from the WebSocket close callback:

- `beforeHandshake`: checks the request and prepares attributes.
- `afterHandshake`: observes the result of handshake processing.
- `WebSocketHandler.afterConnectionEstablished`: runs when the WebSocket session is opened.
- `WebSocketHandler.afterConnectionClosed`: runs when the session closes.
- With STOMP, you can listen for `SessionConnectEvent`, `SessionConnectedEvent`, `SessionSubscribeEvent`, and `SessionDisconnectEvent` depending on the purpose.

Do not use `afterHandshake` to clear connection state because at that moment the session may have just been created and is still active. Per-session registered resources should be released when `afterConnectionClosed` or the corresponding disconnect event occurs. A disconnect may be emitted multiple times depending on the transport; the cleanup operation should be idempotent.

If you need to manage a list of sessions per user, use a thread-safe structure and remove the entry on disconnect. You need to handle reconnects, multiple tabs/browsers of the same user, and session expiry. With STOMP user destinations, prefer Spring's user registry mechanism instead of assuming each user has only one connection.

## 13. HttpSession and WebSocket Lifetime

The HTTP session and the WebSocket session have different lifecycles. WebSocket is a long-lived connection; the HTTP session may expire while the socket is still open. If the application relies on the HTTP session, you need to decide how to handle it when the session expires or the user logs out:

- Close the WebSocket session when the user logs out or has permissions revoked.
- Check permissions on sensitive messages, especially if permissions can change while the connection is still open.
- Consider Spring Session WebSocket integration if you need to coordinate the HTTP session lifetime with the WebSocket session.
- Do not treat handshake authentication as an indefinite permit; a token/session may expire or be revoked.

Copying a value from the HTTP session into the WebSocket attributes does not make that value update automatically when the HTTP session changes. If the data can change, read from an appropriate state source or provide an update/revocation mechanism.

## 14. Testing HandshakeInterceptor and Principal

A test suite should cover both the handshake and the messages after connecting:

1. The request has a valid Principal and an allowed tenant: the handshake succeeds, and `tenantId` is present in `WebSocketSession.getAttributes()`.
2. The request has no Principal: the handshake is rejected with an appropriate status.
3. The Principal has no permission for the requested tenant: the handshake is rejected.
4. The tenant header is missing, empty, or malformed: no session is created.
5. The HTTP session interceptor only copies the attributes in the allowlist and does not copy the session ID when the option is turned off.
6. The raw WebSocket handler receives the correct `session.getPrincipal()`.
7. The STOMP controller receives the correct Principal of the HTTP-authenticated user.
8. A valid CONNECT token gets a user attached; an invalid token is rejected.
9. A user without permission cannot SEND to or SUBSCRIBE to a forbidden destination.
10. Disconnect cleans up the session/resources exactly once in business terms.

Unit tests can call `beforeHandshake` directly with a fake request/response to check the allow and reject branches. Integration tests with a real WebSocket client and server help confirm that the upgrade, cookie, Principal propagation, session attributes, and STOMP channel security work together.

## 15. Common Mistakes

- **Confusing `afterHandshake` with the WebSocket close event:** a completed handshake does not mean the connection has ended; cleanup belongs to the disconnect callback.
- **Not checking the return value of `beforeHandshake`:** returning `false` is how you reject the handshake; you need to set an appropriate status so the client receives a clear result.
- **Trusting the tenant ID or user ID from the client:** every value the client sends must be verified against the Principal and server-side permissions.
- **Copying the entire HTTP session by default:** this can bring tokens, security state, or internal objects into the WebSocket attributes; prefer an allowlist.
- **Treating handshake attributes as the Principal:** attributes are application context; the Principal is the authenticated identity.
- **Using `HttpSessionHandshakeInterceptor` to authenticate:** this interceptor copies session data; it does not verify credentials or access rights.
- **Using `HandshakeInterceptor` to block each STOMP SEND:** you need a `ChannelInterceptor` or Spring Security message authorization.
- **Trusting STOMP login/passcode over WebSocket:** Spring ignores those two headers by default and uses the identity from the HTTP handshake.
- **Putting a token in the query string:** the token can appear in logs or the URL history.
- **Only checking Origin:** an origin allowlist does not replace authentication and authorization.
- **Assuming the Principal is never null:** an endpoint for anonymous users needs separate handling; a private endpoint must require authentication.
- **Not handling session expiry or logout:** the socket can persist after the HTTP session changes or expires.

## 16. Deployment Process

1. Choose raw WebSocket or STOMP; determine where the handshake is handled and where messages are handled.
2. Protect the HTTP endpoint with Spring Security to authenticate the handshake request.
3. Register a `HandshakeInterceptor` for additional checks and to prepare verified attributes.
4. Only copy the HTTP session attributes that are truly necessary; consider turning off copying the session ID.
5. Read the `Principal` from the `WebSocketSession` or the controller parameter; use attributes for tenant/locale/context.
6. If using a token in STOMP CONNECT, authenticate with a `ChannelInterceptor` and attach the user via `accessor.setUser(...)`.
7. Configure the origin allowlist, CSRF, and message authorization according to the threat model.
8. Clean up resources in the disconnect callback or the STOMP disconnect event.
9. Test handshake failure, Principal propagation, tenant isolation, invalid token, SEND/SUBSCRIBE authorization, and session expiration.
10. Monitor the number of connections, handshake failures, disconnects, authentication failures, and authorization errors without logging credentials.

## 17. Conclusion

`HandshakeInterceptor` intervenes in the HTTP WebSocket handshake: `beforeHandshake` checks the request and adds attributes, while `afterHandshake` observes the result of the handshake process. The attributes are copied into `WebSocketSession.getAttributes()` for the handler to use throughout the connection.

`Principal` represents the authenticated user and is automatically passed by Spring from the HTTP request to the WebSocket/STOMP session in the ordinary HTTP authentication model. `HttpSessionHandshakeInterceptor` only copies HTTP session data; an allowlist is needed to avoid carrying sensitive data into the WebSocket. For STOMP token authentication, use a `ChannelInterceptor` at the CONNECT frame. Combine authentication, origin validation, authorization, session cleanup, and disconnect testing to protect the entire connection lifecycle.

## References

- [Spring Framework Reference — WebSocket API and Handshake](https://docs.spring.io/spring-framework/reference/web/websocket/server.html)
- [Spring Framework Javadoc — HandshakeInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/server/HandshakeInterceptor.html)
- [Spring Framework Javadoc — HttpSessionHandshakeInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/server/support/HttpSessionHandshakeInterceptor.html)
- [Spring Framework Javadoc — WebSocketSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/WebSocketSession.html)
- [Spring Framework Reference — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework Reference — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Spring Security Reference — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)