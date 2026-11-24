# Object-Level Business Authorization Beyond Destination Checks

## Objective

In STOMP over WebSocket, Spring Security can match a destination such as `/app/orders/**` and require the sender to have the `ORDER_WRITE` authority. This rule is useful for controlling the type of operation, but it is not enough to determine whether a user has permission to act on a specific order.

For example, two users both hold `ORDER_WRITE`. User Alice has permission to cancel her own order, but must not cancel Bob's order. If only the destination `/app/orders/123/cancel` is checked, Alice could try swapping the ID to Bob's order. The path still matches the pattern and the authority is still valid.

You must also enforce **object-level business authorization** (object-level authorization): load or query the target object, then verify the current user's permissions against that exact object, within the right tenant, ownership relationship, role, and business state.

This article presents two critical enforcement points:

- For STOMP `MESSAGE` sent to `/app/**`, enforce object permissions inside the business service, typically using method security.
- For STOMP `SUBSCRIBE` to a destination representing an object such as `/topic/orders/{orderId}`, enforce object read permissions directly in inbound message authorization before the broker registers the subscription.

## 1. Destination authorization vs. object authorization

These two checks answer two different questions:

| Check | Question | Example |
|---|---|---|
| Authentication | Who is connecting? | Principal is `alice` |
| Destination authorization | Can the user send/subscribe to this message type? | Only `ORDER_WRITE` can send to `/app/orders/**` |
| Object-level authorization | Does the user have permission on the specific record? | Alice can only cancel orders owned by Alice |
| Business rule | Is the action valid under the business state? | Only `PENDING` orders can be canceled |

Destination patterns only match destination strings and message types. They do not load the order, do not know whether the user belongs to the order's tenant, and do not verify the order's status.

Never take an object ID, username, tenant, or ownership from the client payload as proof. A client can tamper with all of those values. Identity must come from the server-verified `Authentication`/`Principal`; the relationship to the object must be verified using server-side data.

## 2. Identifying enforcement points by STOMP message type

STOMP has two inbound message types that typically require separate control:

- **MESSAGE**: the client sends data into the application, e.g., `SEND /app/orders/{orderId}/cancel`. Spring routes this message to `@MessageMapping`; the controller calls the business service.
- **SUBSCRIBE**: the client registers to receive data, e.g., `SUBSCRIBE /topic/orders/{orderId}`. The broker can handle the subscription directly without passing through a `@MessageMapping` method.

Therefore:

- For MESSAGE, destination matchers can check general authorities; the service must still verify permissions on the object before reading or modifying it.
- For SUBSCRIBE, object read permissions must be checked directly during message authorization. Allowing subscriptions just because a user has a general role lets the user subscribe to topics of objects belonging to someone else.

Spring Security protects `clientInboundChannel`; it does not run separate authorization on every message on `clientOutboundChannel`. A vital way to prevent data leaks is to allow only subscriptions that the user is authorized to create.

## 3. Configuring general permissions for STOMP

Example using Spring Security 7 and `AuthorizationManager`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
@EnableMethodSecurity
public class WebSocketSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages,
            OrderSubscriptionAuthorizationManager orderSubscriptionAuthorizationManager) {

        messages
                .nullDestMatcher().authenticated()
                .simpSubscribeDestMatchers("/topic/orders/{orderId}")
                    .access(orderSubscriptionAuthorizationManager)
                .simpMessageDestMatchers("/app/orders/**")
                    .hasAuthority("ORDER_WRITE")
                .simpTypeMatchers(SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE)
                    .denyAll()
                .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

Meaning:

- `@EnableWebSocketSecurity` enables authorization integration for STOMP messages.
- `@EnableMethodSecurity` enables annotations such as `@PreAuthorize` on services.
- `nullDestMatcher().authenticated()` requires authentication for messages without a destination, such as CONNECT or DISCONNECT.
- `simpSubscribeDestMatchers(...)` matches only SUBSCRIBE frames with the specified destination.
- `simpMessageDestMatchers(...)` matches only MESSAGE frames, i.e., clients sending to application handlers.
- `denyAll()` denies remaining MESSAGE/SUBSCRIBE frames without an allow rule.
- `anyMessage().denyAll()` is the final rule so a newly added unconfigured message type is not accidentally allowed.

Matcher order matters: Spring uses the first matching rule. Place specific rules before broad deny rules.

This is an illustrative allowlist. A real application needs to add each public or private destination according to its policy while keeping the default-deny rule at the end.

## 4. Object authorization when the client sends MESSAGE

Suppose the client sends an order cancellation command to the destination:

~~~text
/app/orders/7f1d6c3e-1d5b-4d7c-9f7a-9f1d4c8c7a10/cancel
~~~

The controller receives the ID from the destination and the command payload:

~~~java
import java.util.UUID;
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
public class OrderMessageController {

    private final OrderCommandService orderCommandService;

    public OrderMessageController(OrderCommandService orderCommandService) {
        this.orderCommandService = orderCommandService;
    }

    @MessageMapping("/orders/{orderId}/cancel")
    public void cancel(
            @DestinationVariable UUID orderId,
            @Payload CancelOrderCommand command) {

        orderCommandService.cancelOrder(orderId, command);
    }
}
~~~

With the application prefix `/app` configured, the actual destination from the client is `/app/orders/{orderId}/cancel`. The controller accepts only the ID and command; it never trusts an `ownerUsername` or `tenantId` field sent by the client.

Place the permission check on the business service so other callers such as HTTP controllers, scheduled jobs, or other services cannot bypass the rule:

~~~java
import java.util.UUID;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCommandService {

    private final OrderRepository orderRepository;

    public OrderCommandService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @PreAuthorize("@orderAccess.canCancelOrder(authentication, #orderId)")
    @Transactional
    public void cancelOrder(
            @P("orderId") UUID orderId,
            CancelOrderCommand command) {

        Order order = orderRepository.findById(orderId)
                .orElseThrow(OrderNotFoundException::new);

        // Re-check the invariant inside the transaction before modifying state.
        if (order.getStatus() != OrderStatus.PENDING) {
            throw new IllegalStateException("Only pending orders can be cancelled");
        }

        order.cancel(command.reason());
    }
}
~~~

`@PreAuthorize` is evaluated before the service method runs. The `orderAccess` bean checks whether the current user has permission to cancel that specific order. `@P("orderId")` names the parameter explicitly so the `#orderId` expression works reliably across compilation settings.

The service method must be invoked through a Spring bean proxy for method security to take effect. Internal calls on the same object via self-invocation bypass the proxy and can skip the interceptor.

## 5. Writing an object-level permission policy

A policy bean can consolidate ownership, tenant, membership, and status logic:

~~~java
import java.util.UUID;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("orderAccess")
public class OrderAccessService {

    private final OrderRepository orderRepository;

    public OrderAccessService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public boolean canCancelOrder(
            Authentication authentication,
            UUID orderId) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        return orderRepository.findByIdAndOwnerUsername(
                        orderId,
                        authentication.getName())
                .map(order -> order.getStatus() == OrderStatus.PENDING)
                .orElse(false);
    }

    public boolean canReadOrder(String username, String rawOrderId) {
        final UUID orderId;

        try {
            orderId = UUID.fromString(rawOrderId);
        }
        catch (IllegalArgumentException ex) {
            return false;
        }

        return orderRepository.existsByIdAndOwnerUsername(orderId, username);
    }
}
~~~

Illustrative repository methods:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, UUID> {

    Optional<Order> findByIdAndOwnerUsername(UUID id, String ownerUsername);

    boolean existsByIdAndOwnerUsername(UUID id, String ownerUsername);
}
~~~

The example checks the owner for readability. In a multi-tenant system, queries must include the current tenant, e.g., `existsByIdAndOwnerUsernameAndTenantId(...)`. If permissions are based on groups, projects, or sharing relationships, the policy must check the corresponding membership. Never load an object by ID and check only a generic role while skipping tenant or ownership checks.

Returning `false` when the ID is invalid, the object does not exist, or the user lacks permission avoids inadvertently revealing to clients whether a private record exists. Depending on API policy, the application can map these cases to the same access error.

## 6. Object authorization when a client SUBSCRIBEs to a topic by ID

A subscription such as `/topic/orders/{orderId}` can be handled directly by the broker. Therefore, placing checks in a `@MessageMapping` controller is insufficient; no controller is invoked when a client only SUBSCRIBEs.

Spring Security lets you attach an `AuthorizationManager<MessageAuthorizationContext<?>>` to a matcher. The context contains the message and path variables extracted from the destination pattern.

Create a dedicated manager:

~~~java
import java.util.function.Supplier;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.messaging.access.intercept.MessageAuthorizationContext;
import org.springframework.stereotype.Component;

@Component
public class OrderSubscriptionAuthorizationManager
        implements AuthorizationManager<MessageAuthorizationContext<?>> {

    private final OrderAccessService orderAccess;

    public OrderSubscriptionAuthorizationManager(OrderAccessService orderAccess) {
        this.orderAccess = orderAccess;
    }

    @Override
    public AuthorizationResult authorize(
            Supplier<? extends Authentication> authentication,
            MessageAuthorizationContext<?> context) {

        Authentication current = authentication.get();
        String orderId = context.getVariables().get("orderId");

        boolean granted = current != null
                && current.isAuthenticated()
                && !(current instanceof AnonymousAuthenticationToken)
                && orderId != null
                && orderAccess.canReadOrder(current.getName(), orderId);

        return new AuthorizationDecision(granted);
    }
}
~~~

Matcher in the security configuration:

~~~java
.simpSubscribeDestMatchers("/topic/orders/{orderId}")
    .access(orderSubscriptionAuthorizationManager)
~~~

Spring extracts `orderId` from the destination according to the pattern and puts it into `context.getVariables()`. The manager retrieves the sender's Authentication, then invokes the server-side policy to verify whether the user has permission to read that order. If the ID is missing, malformed, nonexistent, or does not belong to the user, the manager returns a deny decision.

This is the key difference between `simpSubscribeDestMatchers` and `simpMessageDestMatchers`: the former handles only SUBSCRIBE, while the latter handles only MESSAGE.

## 7. Separating command-send permissions from topic-read permissions

A user may be allowed to read an order without being allowed to cancel it. Conversely, an administrative service may be allowed to cancel an order under a support workflow without automatically being allowed to subscribe to every private topic.

Define policies per action:

| Action | Destination / entry point | Policy |
|---|---|---|
| Cancel order | MESSAGE `/app/orders/{id}/cancel` | Holds command authority, is order owner or has appropriate admin permission, valid status |
| Watch order | SUBSCRIBE `/topic/orders/{id}` | Has permission to read the order within the tenant |
| Receive personal notifications | SUBSCRIBE `/user/queue/notifications` | Correct authenticated user and user session |
| Send message directly to topic | MESSAGE `/topic/**` | Usually denied for clients to prevent spoofing server notices |

Do not use a single `hasRole("USER")` check for every action on every object. A role only describes general capability; permission on an individual record requires checking the specific context.

## 8. Authentication and client-supplied data

In typical web applications, Spring attaches the authenticated `Principal` from the HTTP handshake to the WebSocket session and subsequent STOMP messages. Clients must not pick their own identity by sending a `username` field in the payload.

With token authentication, the application can validate a token at STOMP CONNECT using a `ChannelInterceptor` and then call `StompHeaderAccessor.setUser(authentication)`. The authentication interceptor must run before the authorization interceptor so `Authentication` is ready when Spring Security evaluates messages.

In addition:

- Keep appropriate origin rules and CSRF mechanisms for STOMP CONNECT per Spring Security configuration.
- Never trust `ownerId`, `tenantId`, `role`, or `isAdmin` sent by the client.
- Check permissions on the server on every data access path, including REST, STOMP, batch, or scheduled jobs.
- Validate payloads separately from authorization. Syntactically valid data can still be unauthorized for that object.
- Never allow clients to send MESSAGE directly to internal broker destinations or server-only topics.

## 9. Revoking permissions while a subscription is active

Authorization on SUBSCRIBE is checked when the client registers the subscription. If a user is later removed from a group or loses access, an existing subscription may remain open and continue receiving messages.

If permissions can change while a WebSocket remains open, handle revocation explicitly:

1. When membership or access is revoked, locate the affected sessions/subscriptions.
2. Unsubscribe or close the session per application policy, or apply an appropriate broker ACL mechanism.
3. For sensitive data, consider re-checking permissions on the publishing path before sending or delivering via appropriate user destinations.
4. Do not rely on the initial SUBSCRIBE check as a guarantee that permission will last forever.

Spring Security does not check authorization separately on each outbound message; protecting subscriptions and handling revocation are essential parts of the design.

## 10. Performance and data consistency

Object-level authorization may require querying the database for every message or subscription. To preserve performance:

- Use narrow queries such as `existsByIdAndOwnerUsernameAndTenantId` instead of loading entire entity graphs.
- Index the ID, owner, tenant, and membership columns used in policies.
- Cache permission decisions only when a clear invalidation strategy exists; stale caches can retain revoked permissions.
- For write operations, check state and modify data within the same transaction; consider optimistic/pessimistic locking under contention.
- Return a deny decision when permissions cannot be verified. Database or policy service errors must never fail open to allow.

In particular, the check inside `@PreAuthorize` and the write inside the service may occur separately. Therefore, the service must still enforce business invariants inside the transaction to prevent state changes between authorization and update.

## 11. Testing object-level authorization

A useful test suite should verify both allowed paths and denied paths:

| Scenario | Expected outcome |
|---|---|
| Alice has `ORDER_WRITE` and owns the PENDING order | Allow MESSAGE to cancel order |
| Alice has `ORDER_WRITE`, but order belongs to Bob | Deny MESSAGE even though destination matches |
| Alice owns the order, but order is already SHIPPED | Deny cancellation due to business rule |
| Alice subscribes to her own order's topic | Allow SUBSCRIBE |
| Alice subscribes to Bob's order topic | Deny SUBSCRIBE |
| Unauthenticated or anonymous user | Deny private destinations |
| Malformed or nonexistent ID | Deny |
| Client sends MESSAGE directly to `/topic/orders/**` | Deny |
| Membership is revoked after subscribing | System executes subscription or session revocation flow |

Recommended tests:

- Unit tests for `OrderAccessService` covering owner, outsider, other tenant, and order statuses.
- Unit tests for `OrderSubscriptionAuthorizationManager` covering missing path variables, null authentication, and different policy outcomes.
- STOMP integration tests verifying MESSAGE is blocked before the controller when lacking authority and SUBSCRIBE is blocked before the broker when lacking read permission.
- Method security tests invoking the service through the Spring proxy to ensure `@PreAuthorize` is actually enforced.

Testing destination matchers alone is not enough to prove object-level authorization works. Test with two distinct identities and objects with different ownership relationships.

## Key takeaways

- Destination authorization checks message type and path; object-level authorization checks permissions on the actual record.
- Clients must never dictate owner, tenant, or identity via payloads.
- For MESSAGE to `/app/**`, enforce object permissions in business services, e.g., with `@PreAuthorize`.
- For SUBSCRIBE to ID-based topics, use a custom `AuthorizationManager<MessageAuthorizationContext<?>>` and `context.getVariables()`.
- Separate read permissions, write permissions, and business rules per action.
- Spring Security inspects the inbound channel; protect subscriptions to control outbound data.
- When permissions are revoked, handle existing active subscriptions as well.
- For write operations, re-check invariants inside the transaction to avoid race conditions.

## References

- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/7.0/servlet/integrations/websocket.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/architecture.html)
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-annotations.html)
- [MessageAuthorizationContext API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/messaging/access/intercept/MessageAuthorizationContext.html)
