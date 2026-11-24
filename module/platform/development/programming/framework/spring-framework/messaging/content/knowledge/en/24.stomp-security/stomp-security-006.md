# Preventing User, Tenant, and Destination Spoofing in STOMP

## Objective

In a Spring WebSocket application using STOMP, clients can send payloads, native headers, destinations, and SEND or SUBSCRIBE commands. Because this data originates from the client, it can be modified using a browser, script, or another STOMP client. If the server trusts fields such as senderId, userId, tenantId, role, or destination declared by the client, users can impersonate another identity, access another tenant's data, or send messages posing as the system.

STOMP security must be enforced across multiple layers:

1. **Authentication** determines who is connecting and binds the verified identity to the Principal.
2. **Message authorization** decides whether the Principal is allowed to SEND or SUBSCRIBE to a specific destination.
3. **Business authorization** verifies whether the user has permission to operate on the exact tenant, room, order, or resource.
4. **Server-side routing** ensures the server decides the outbound destination, never accepting an arbitrary target destination from the client payload.

No destination matcher can replace permission checks on business data. A destination tells where a message goes; it does not prove the sender has permission to access the resource there.

## 1. Values a client can spoof

Treat all client-sent information as untrusted input, including:

| Data | Spoofing example | Risk if the server trusts it directly |
|---|---|---|
| senderId or userId in payload | Sending an administrator's senderId | Message or action is attributed to someone else |
| role or isAdmin | Sending role=ADMIN | Privilege escalation |
| tenantId | Changing tenantId from current tenant to another tenant | Cross-tenant data read or write |
| destination | Sending SEND directly to /topic/system/notifications | Impersonating server-emitted messages |
| native header user or tenant | Manually adding userId, tenantId, role to CONNECT or SEND | Overriding security context if handled improperly by the server |
| recipient or targetUserId | Choosing someone else's ID | Sending data to an unauthorized recipient |
| roomId, orderId, or resourceId | Swapping the ID in destination or payload | Accessing out-of-scope resources |

Even when clients use the official UI, users can still alter STOMP frames. Client-side checks in JavaScript only improve UX; security decisions must live on the server.

## 2. Authenticating at HTTP handshake and using Spring's Principal

For applications with HTTP login via Spring Security, the simplest approach is to authenticate the WebSocket handshake with the same HTTP security mechanism. Each STOMP session is then bound to the authenticated request's Principal.

Basic flow:

1. The user logs in over HTTP.
2. Spring Security authenticates the request and stores the Authentication in the SecurityContext.
3. The browser opens the WebSocket handshake using a valid session cookie.
4. Spring associates the HTTP request's Principal with the WebSocket session.
5. Subsequent STOMP messages on that session carry that authenticated user.

In a handler, receive the Principal directly:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
public class AccountController {

    @MessageMapping("/account/ping")
    public String ping(Principal principal) {
        if (principal == null) {
            throw new IllegalStateException("STOMP session is not authenticated");
        }

        return "Hello " + principal.getName();
    }
}
~~~

Principal is the identity established by the server through authentication. Do not replace it with senderId in the payload, userId in a native header, or a self-declared username from the client.

STOMP has login and passcode headers on the CONNECT frame. With STOMP over WebSocket in Spring, Spring ignores these headers for authentication by default and expects the identity to already be authenticated at the HTTP layer. Never assume that sending login or passcode in CONNECT automatically produces a trustworthy Principal.

## 3. Token authentication at STOMP CONNECT without cookie sessions

Some SPA, mobile, or stateless API applications use access tokens instead of HTTP sessions. The browser WebSocket API does not allow arbitrarily adding custom HTTP headers to the handshake. Spring supports authenticating tokens at the STOMP layer:

1. The client sends the token in a native header of the CONNECT frame.
2. The server reads that header inside a ChannelInterceptor.
3. The server verifies the signature, issuer, audience, expiration, and required claims.
4. The server creates an Authentication from the verified identity.
5. The server calls setUser on StompHeaderAccessor.
6. Spring attaches that user to subsequent messages within the same session.

Client example using a STOMP library:

~~~javascript
stompClient.connect(
    { Authorization: "Bearer " + accessToken },
    onConnected,
    onError
);
~~~

This is an illustrative client example; method names may vary depending on the STOMP library version. Do not place tokens in the WebSocket URL query string because URLs can appear in access logs, proxy logs, or monitoring systems.

Server-side interceptor example:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class StompConnectAuthenticationInterceptor
        implements ChannelInterceptor {

    private final TokenAuthenticationService tokenAuthenticationService;

    public StompConnectAuthenticationInterceptor(
            TokenAuthenticationService tokenAuthenticationService) {
        this.tokenAuthenticationService = tokenAuthenticationService;
    }

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor =
                MessageHeaderAccessor.getAccessor(
                        message, StompHeaderAccessor.class);

        if (accessor == null) {
            return message;
        }

        if (StompCommand.CONNECT.equals(accessor.getCommand())) {
            String authorization =
                    accessor.getFirstNativeHeader("Authorization");

            Authentication authentication =
                    tokenAuthenticationService.authenticateBearer(authorization);

            accessor.setUser(authentication);
        }

        return message;
    }
}
~~~

TokenAuthenticationService is a service implemented by the application. It must reject tokens that are missing, have invalid signatures, are expired, have the wrong issuer or audience, are revoked if revocation is supported, or lack access permissions for the application. The authenticateBearer method must return an Authentication only after successful verification; it must never construct an Authentication merely from a userId string sent by the client.

Register the interceptor before Spring Security's authorization interceptor:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
public class StompAuthenticationConfig
        implements WebSocketMessageBrokerConfigurer {

    private final StompConnectAuthenticationInterceptor authenticationInterceptor;

    public StompAuthenticationConfig(
            StompConnectAuthenticationInterceptor authenticationInterceptor) {
        this.authenticationInterceptor = authenticationInterceptor;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(authenticationInterceptor);
    }
}
~~~

Per Spring guidance, the authentication interceptor must run before Spring Security's authorization interceptor. Separating this configuration into its own WebSocketMessageBrokerConfigurer with the proper precedence order ensures the Authentication is attached before authorization rules evaluate messages.

If using HTTP session authentication, do not add this token interceptor. Choose one authentication mechanism that fits the application's architecture and avoid inadvertently allowing an unauthenticated connection through a fallback path.

## 4. Authorizing SEND and SUBSCRIBE with Spring Security

Authentication only answers who is connecting. Spring Security WebSocket authorization decides which destinations that person can send messages to or subscribe to.

Enable message security support with @EnableWebSocketSecurity and declare an AuthorizationManager:

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
public class StompAuthorizationConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/**").hasRole("USER")
            .simpSubscribeDestMatchers("/topic/public/**").authenticated()
            .simpSubscribeDestMatchers("/user/queue/**").hasRole("USER")
            .simpDestMatchers("/topic/**", "/queue/**").denyAll()
            .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

This is an illustrative policy for an application requiring every session to be authenticated. The hasRole("USER") rule requires an Authentication with authority ROLE_USER:

- Messages without a destination, such as session control frames, require an authenticated user.
- SEND to /app/** is permitted for users with role USER.
- SUBSCRIBE to /topic/public/** is permitted only after authentication.
- SUBSCRIBE to /user/queue/** requires role USER.
- Clients cannot SEND directly to /topic/** or /queue/**.
- MESSAGE and SUBSCRIBE types not matching an allow rule are denied.
- Remaining messages are also denied by default.

The key point is that **MESSAGE and SUBSCRIBE are two separate permissions**. A client may be allowed to subscribe to a topic without being allowed to send messages to that topic. Allowing clients to SEND directly to a system topic lets them spoof server-emitted messages. Spring Security recommends blocking MESSAGE from clients to broker destinations such as /topic/** and /queue/**.

Likewise, do not let clients arbitrarily SUBSCRIBE to internal queues. In particular, never let clients subscribe directly to physical broker queues if doing so could expose another user's messages. Use user destinations or controlled destinations.

Matcher ordering matters: specific rules must come before general rules. For example, the rule allowing /topic/public/** must appear before the rule denying unmatched MESSAGE or SUBSCRIBE frames.

For an application allowing anonymous users to connect, you must deliberately redesign CONNECT and CSRF rules. Never simply switch all rules to permitAll, as that removes the message control layer.

## 5. Preventing clients from spoofing system-emitted messages

Suppose the server broadcasts maintenance notices to /topic/system/notifications. Clients may SUBSCRIBE to receive notices, but must not SEND to that destination themselves.

A secure policy usually looks like this:

| Operation | Destination | Permission |
|---|---|---|
| Client SEND | /app/notifications | Allowed if authenticated and business checks pass |
| Client SUBSCRIBE | /topic/system/notifications | May allow authenticated users |
| Client SEND | /topic/system/notifications | Deny |
| Client SEND | /queue/** | Deny by default |
| Client SUBSCRIBE | Broker's internal physical queues | Deny |
| Server SEND | /topic/system/notifications | Allowed per server's internal permissions |

The server emits system events only after determining the content and destination itself:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class SystemNotificationPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public SystemNotificationPublisher(
            SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishMaintenanceNotice(String message) {
        messagingTemplate.convertAndSend(
                "/topic/system/notifications",
                new SystemNotification(message)
        );
    }
}

record SystemNotification(String message) {}
~~~

Clients have no ability to invoke this server method directly. Messages are emitted only by the server component after applying business policies.

Do not take a destination from the payload, such as command.getDestination(), and pass it straight into convertAndSend. If the destination must be chosen by business logic, the server must map a validated choice to a fixed destination or construct the destination from IDs whose access rights have been verified.

## 6. Using user destinations to send private messages

When sending a private reply to the current user, obtain the recipient name from the Principal or from a verified Authentication object. Do not accept a recipient username sent by the client and trust it directly.

Example of the server sending a private reply:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
public class PrivateMessageController {

    private final SimpMessagingTemplate messagingTemplate;

    public PrivateMessageController(
            SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @MessageMapping("/private/ping")
    public void ping(Principal principal) {
        String authenticatedUser = principal.getName();

        messagingTemplate.convertAndSendToUser(
                authenticatedUser,
                "/queue/reply",
                new PrivateReply("Pong")
        );
    }
}

record PrivateReply(String message) {}
~~~

The client subscribes to /user/queue/reply. Spring resolves the user destination to a private destination for the corresponding user or session. The client does not need to know the broker's physical queue.

If the server needs to send to another user, the recipient must be obtained from validated business data. For example, a service verifies that user A is permitted to message user B in the same conversation before calling convertAndSendToUser. Never treat a client-supplied username as proof that the recipient is valid.

## 7. Preventing tenant spoofing

In a multi-tenant system, every request must be bound to a tenant the user has been granted access to. The tenant ID may appear in URLs, STOMP destinations, payloads, or JWT claims, but not all locations have equal trustworthiness.

Rules to uphold:

1. Obtain the user identity from the authenticated Principal.
2. Verify the user has membership or access rights to the requested tenant.
3. Verify the resource belongs to that tenant before reading or modifying it.
4. Include the verified tenant ID in every database query.
5. Construct outbound destinations from the tenant and resource confirmed by the server.
6. Never trust tenantId sent by the client in payloads or native headers.

An example payload might contain fields a client attempts to spoof:

~~~java
public record ChatCommand(
        String senderId,
        String tenantId,
        String text
) {}
~~~

The handler does not use senderId or tenantId from the payload. It retrieves the user from Principal, verifies membership in the selected tenant, verifies the room belongs to the tenant, and creates a new event using server-confirmed data:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
public class TenantChatController {

    private final TenantAccessService tenantAccessService;
    private final RoomAccessService roomAccessService;
    private final SimpMessagingTemplate messagingTemplate;

    public TenantChatController(
            TenantAccessService tenantAccessService,
            RoomAccessService roomAccessService,
            SimpMessagingTemplate messagingTemplate) {
        this.tenantAccessService = tenantAccessService;
        this.roomAccessService = roomAccessService;
        this.messagingTemplate = messagingTemplate;
    }

    @MessageMapping("/tenants/{tenantId}/rooms/{roomId}/messages")
    public void send(
            @DestinationVariable("tenantId") String tenantId,
            @DestinationVariable("roomId") String roomId,
            ChatCommand command,
            Principal principal) {

        String userId = principal.getName();

        Tenant tenant =
                tenantAccessService.requireMembership(userId, tenantId);

        Room room =
                roomAccessService.requireCanPost(userId, tenant.id(), roomId);

        ChatEvent event = new ChatEvent(
                userId,
                tenant.id(),
                room.id(),
                command.text()
        );

        String destination =
                "/topic/tenants/" + tenant.id() + "/rooms/" + room.id();

        messagingTemplate.convertAndSend(destination, event);
    }
}

record ChatEvent(
        String senderId,
        String tenantId,
        String roomId,
        String text
) {}
~~~

TenantAccessService and RoomAccessService are business services implemented by the application. They must reject the request if the user does not belong to the tenant or if the room does not belong to the verified tenant. If Principal is null, the request must already be rejected at the authentication/authorization layer before the handler executes.

In the example, tenantId on the inbound destination is only **the tenant the client requested to access**. It is not yet a valid tenant until tenantAccessService verifies membership. Similarly, roomId must be verified to belong to that tenant. The server constructs the event from the verified userId, tenant.id(), and room.id(); the senderId and tenantId fields in the payload are ignored.

### Tenant scope must enter data queries

You should not check the tenant only in the controller and then call a repository by global resource ID. Every read, update, or delete query must bind the tenant as well:

~~~java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface RoomRepository extends JpaRepository<Room, String> {

    Optional<Room> findByIdAndTenantId(String roomId, String tenantId);
}
~~~

The service uses the tenant-scoped query:

~~~java
public Room requireCanPost(
        String userId,
        String tenantId,
        String roomId) {

    membershipService.requireMember(userId, tenantId);

    Room room = roomRepository
            .findByIdAndTenantId(roomId, tenantId)
            .orElseThrow(ResourceNotFoundException::new);

    permissionService.requireCanPost(userId, room);

    return room;
}
~~~

This is an illustrative repository/service example; entity and exception names depend on the application. Querying by the pair of ID and tenant helps prevent cross-tenant access bugs caused by omitting a filter condition.

If the tenant ID resides in a JWT, use the claim only after the token has been verified. For users who can belong to multiple tenants or whose membership can be revoked, check current membership or use a permission cache with proper expiration and invalidation. Stale claims in a token should not preserve revoked permissions indefinitely.

## 8. Protecting tenant topics on SUBSCRIBE

Checking membership in the SEND handler is not enough. A client might not send messages yet still SUBSCRIBE to another tenant's topic to eavesdrop on data.

For topics shaped like /topic/tenants/{tenantId}/..., the server needs to check permissions right at SUBSCRIBE time. You can use a custom AuthorizationManager or ChannelInterceptor to:

1. Read the destination of the SUBSCRIBE frame.
2. Retrieve the authenticated Principal from the message.
3. Parse the tenant ID according to a controlled destination pattern.
4. Check the Principal's membership in that tenant.
5. Reject the subscription if the tenant is invalid or the user lacks permission.

Broad pattern rules like /topic/** only check prefixes. They do not know which tenant belongs to which user. A dynamic authorization step based on the Principal and the tenant ID in the destination is needed.

If tenant-wide broadcasting is not needed, consider using /user/queue/** to send privately per Principal. This reduces the places where clients can choose a tenant destination. When tenant topics exist, restrict the pattern and verify SUBSCRIBE permissions per tenant.

Do not allow SUBSCRIBE to physical queues such as /queue/user/messages-123 or internal broker-generated destinations. User destinations are a logical interface for clients; physical queues must be managed by Spring and the broker.

## 9. Destinations are routing addresses, not proof of permission

Common prefixes have distinct meanings:

| Prefix | Purpose | Common policy |
|---|---|---|
| /app/** | Messages from clients entering controllers | Allow SEND after authentication and business checks |
| /topic/** | Broadcast publish/subscribe channels | Allow controlled SUBSCRIBE; deny SEND from clients |
| /queue/** | Broker queues | Strictly restricted; typically deny direct client SEND and SUBSCRIBE |
| /user/** | Logical destinations for a single user | Allow subscribing to private queues per Principal |

A secure destination does not depend solely on its prefix. For instance, /app/orders/{id}/cancel still needs to verify that the user has permission to cancel that specific order. The /app/** matcher only ensures the message goes through an allowed controller area; it does not check order ownership itself.

When constructing destinations from client data:

- Never concatenate an arbitrary destination taken from a payload.
- Never use an unverified tenant ID.
- Never let clients arbitrarily choose /topic, /queue, or /user prefixes.
- Normalize and validate IDs against expected formats.
- Verify the resource belongs to the tenant and the user is permitted to perform the action.
- Prefer a lookup table mapping valid event types to fixed destinations.

## 10. CSRF, Origin, and handshake protection

With Spring Security WebSocket configured via @EnableWebSocketSecurity, inbound STOMP CONNECT requires a valid CSRF token. This protects the application against certain cross-site attacks when browsers automatically send the user's session cookie to the WebSocket endpoint.

Considerations:

- Use HTTPS and WSS in production.
- Restrict the WebSocket endpoint's allowed origins to the list of genuinely permitted domains.
- Keep CSRF protection for STOMP CONNECT when using cookie-based sessions.
- If using tokens in STOMP CONNECT, explicitly design how CSRF tokens are obtained and sent per Spring Security configuration.
- Do not disable CSRF globally just to make WebSocket work.
- Do not treat Origin checks as authentication; non-browser clients can forge this header.
- Do not log tokens, cookies, session IDs, or sensitive payloads.

A CORS/Origin allowlist limits which web pages can open connections from a browser, but it does not replace authentication or authorization. A request with a valid Origin must still pass Principal, destination, and tenant checks.

## 11. Common security mistakes

| Mistake | Why it is dangerous | Fix |
|---|---|---|
| Taking senderId from payload | Clients can impersonate others | Take it from Principal |
| Trusting tenantId from payload | Clients can switch tenants | Verify membership and scope every query |
| Allowing clients to SEND to /topic/** | Enables spoofing system messages | Block MESSAGE to broker prefixes |
| Allowing clients to SUBSCRIBE to /queue/** | Can eavesdrop on another user's queue | Use /user/queue/** and block physical queues |
| Checking roles only on the frontend | Clients can bypass the UI | Enforce authorization in Spring Security and services |
| Protecting only CONNECT | Valid users can call unauthorized destinations | Authorize every MESSAGE and SUBSCRIBE |
| Checking tenant only in the controller | Repository may read another tenant's resource | Scope queries by tenant at the data layer |
| Trusting JWT claims without verification | Token may be forged, expired, or wrong audience | Verify signature, issuer, audience, expiry |
| Sending tokens in query strings | Tokens can leak into access logs | Send tokens in CONNECT headers or suitable HTTP auth |
| Allowing all destinations once authenticated | Users can access out-of-scope features | Allowlist destinations and deny by default |

## 12. Testing anti-spoofing defenses

Tests should prove that the server rejects spoofed frames, not just verify valid cases.

| Scenario | Expected result |
|---|---|
| User A sends a payload containing User B's senderId | Emitted event still takes senderId from Principal A |
| User A sends tenantId of tenant B without membership | Rejected before reading or writing resources |
| User A alters tenantId in a native header | Does not change the verified tenant context |
| Client SEND directly to /topic/system/notifications | Rejected by Spring Security |
| Client SUBSCRIBE to a physical /queue | Rejected |
| User A SUBSCRIBEs to tenant B's tenant topic | Custom tenant authorization rejects it |
| Client sends JWT with invalid signature or expired timestamp | CONNECT is rejected |
| User loses membership after token issuance | Access is revoked according to current membership policy |
| User accesses a room ID belonging to another tenant | Tenant-scoped query finds no resource or returns an access error |
| Client changes destination from /app to /topic | SEND is rejected by the matcher |
| Client sends CONNECT missing CSRF token when using cookie session | CONNECT is rejected |

Test the Spring Security matcher layer, custom tenant authorization, and service/repository layers. Unit tests for services can use a mocked Principal to verify membership checks. Integration tests should send real STOMP frames through the endpoint and verify the server rejects unauthorized operations.

## 13. STOMP security checklist

- [ ] Principal is established from HTTP authentication or a verified token.
- [ ] senderId, userId, role, and tenantId sent by clients are never trusted.
- [ ] If authenticating tokens at CONNECT, the interceptor runs before Spring Security authorization.
- [ ] Every SEND to /app/** undergoes business permission checks.
- [ ] Clients cannot SEND directly to /topic/** or /queue/**.
- [ ] Clients can only SUBSCRIBE to allowlisted destinations.
- [ ] Tenant topics enforce dynamic authorization by Principal and tenant ID.
- [ ] Every repository query is scoped by the verified tenant.
- [ ] User destinations are sent from the server based on Principal.
- [ ] Clients are prevented from subscribing to physical broker queues.
- [ ] CONNECT has CSRF protection when using cookie sessions.
- [ ] Allowed origins are restricted; Origin is not used in place of authentication.
- [ ] Tokens, cookies, sessions, and sensitive payloads do not appear in logs.
- [ ] Tests exist for user, tenant, and destination spoofing as well as cross-tenant access.

## References

- [Spring Framework — Authentication for STOMP over WebSocket](https://docs.spring.io/spring/reference/web/websocket/stomp/authentication.html)
- [Spring Framework — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Spring Framework — STOMP Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html)
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [Spring Framework — STOMP Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html)
