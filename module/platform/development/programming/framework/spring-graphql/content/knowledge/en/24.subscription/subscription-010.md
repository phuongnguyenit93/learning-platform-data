# Authorization for subscriptions

A GraphQL subscription keeps a streaming connection open so the server can push events to the client whenever data changes. Because the stream can live far longer than a typical HTTP request, authorization must be considered at multiple points: when authenticating the connection, when the client registers a subscription operation, when each event is emitted, and when child fields of an event are resolved.

In Spring for GraphQL, subscriptions are typically declared with `@SubscriptionMapping` and return a `Publisher`, `Flux`, or compatible stream type. Spring Security can authenticate callers and protect methods, while the application must ensure each subscriber receives only the events and fields the current principal is permitted to view.

**Authorizing only at subscription start is not enough if permissions can change while the stream is active.** For sensitive data, enforce permissions at the event source or per emitted event, handle permission revocation, and terminate the subscription when needed.

## 1. Authentication and authorization in subscriptions

Two concepts must be kept distinct:

- **Authentication** establishes who the caller is. For example, a valid token maps to a principal and its authorities.
- **Authorization** decides what actions or data that principal is allowed to access. For example, a user may watch their own orders but must not watch orders belonging to another tenant.

An authenticated WebSocket does not mean every GraphQL operation on that connection is allowed. Likewise, a user permitted to open a subscription initially may have that permission revoked while the stream remains alive.

Apply controls across layers:

| Stage | What to verify |
| --- | --- |
| HTTP handshake or connection initialization | Token, session, connection origin, and principal identity |
| Each GraphQL operation | Current principal, permission to invoke the subscription field, and inputs such as accountId/orderId |
| Selecting a topic or subscribing to event source | Whether the principal has permission to subscribe to that resource/tenant |
| Each emitted event | Whether viewing the event is still valid and the event falls within the principal's scope |
| Resolving child fields | Permission to access sensitive fields or related data |
| Token expiration, logout, or permission revocation | Stop emitting events or close the subscription per policy |

Never treat a connection ID, correlation ID, or client-supplied `userId` value as proof of identity. Identity and permissions must come from a server-verified security context.

## 2. Subscriptions in Spring for GraphQL

A schema can declare a subscription for order events:

~~~graphql
type Subscription {
    orderUpdated(orderId: ID!): OrderEvent!
}

type OrderEvent {
    orderId: ID!
    status: String!
    changedAt: String!
}
~~~

An annotated controller can return `Flux<OrderEvent>`:

~~~java
@Controller
public class OrderSubscriptionController {

    private final OrderEventService orderEventService;

    public OrderSubscriptionController(OrderEventService orderEventService) {
        this.orderEventService = orderEventService;
    }

    @SubscriptionMapping
    public Flux<OrderEvent> orderUpdated(@Argument("orderId") UUID orderId) {
        return orderEventService.eventsForOrder(orderId);
    }
}
~~~

The `@SubscriptionMapping` method creates a publisher for the subscription. GraphQL executes the selection set for each emitted event to produce the corresponding GraphQL responses. Therefore, authorization may need to appear both in the subscription resolver and in child field resolvers of the event.

Do not return a preloaded list of events when a continuous stream is required. `Flux`/`Publisher` represents an event source; each subscriber gets its own subscription and must be bound to the appropriate principal and data scope.

## 3. Authenticating the WebSocket handshake and connection_init

GraphQL over WebSocket commonly involves two notable stages:

1. The client establishes a WebSocket connection via an HTTP upgrade handshake.
2. The client sends a `connection_init` message per the GraphQL WebSocket protocol before sending operations.

If the application authenticates at the HTTP handshake, Spring Security can use standard HTTP authentication mechanisms such as a session cookie or a bearer token in headers. This is usually straightforward when the client can attach credentials during the handshake.

Some clients send tokens inside the `connection_init` payload. That payload is merely client-supplied data; it does not automatically become an authenticated principal. The application must use `WebSocketGraphQlInterceptor` or an equivalent integration mechanism to validate the token, construct a trusted security context, and bind the identity safely to the session/execution.

High-level flow:

~~~mermaid
sequenceDiagram
    participant C as GraphQL client
    participant WS as WebSocket endpoint
    participant SI as Security / interceptor
    participant G as GraphQL execution
    C->>WS: HTTP Upgrade + credentials
    WS->>SI: Authenticate handshake
    SI-->>WS: Authenticated session
    C->>WS: connection_init (if used by protocol)
    WS->>SI: Validate init payload if token present
    SI-->>C: connection_ack or reject
    C->>WS: subscription operation
    WS->>G: Execute with principal/context
    G-->>C: Subscription events
~~~

Never trust `userId`, `tenantId`, roles, or permission lists self-declared by the client in the connection payload. If the payload carries an access token, verify its signature, issuer, audience, expiry, and required claims just like a token received from an HTTP header.

A WebSocket connection can outlive the access token's lifetime. Define explicitly what happens when the token expires: reject new operations, terminate active subscriptions, or require the client to reconnect with a fresh token. Never keep granting access indefinitely just because the initial handshake succeeded.

## 4. Authorizing each operation on the same connection

One WebSocket connection can run multiple GraphQL operations. Therefore, authenticating the connection does not replace per-operation checks. For every request, the application must ensure GraphQL execution receives the right principal and context.

Spring for GraphQL provides `WebSocketGraphQlInterceptor` for WebSocket lifecycle events and `WebGraphQlInterceptor` for web-layer GraphQL request handling. Interceptors can add verified data to `GraphQLContext` for resolvers to read during execution.

For example, once the principal has been verified by Spring Security, a resolver can accept `Principal` or read from context:

~~~java
@SubscriptionMapping
public Flux<OrderEvent> orderUpdated(
        @Argument("orderId") UUID orderId,
        Principal principal) {

    return orderEventService.eventsForOrder(
        orderId, principal.getName());
}
~~~

Or use `@ContextValue` if an interceptor placed values into `GraphQLContext`:

~~~java
@SubscriptionMapping
public Flux<OrderEvent> orderUpdated(
        @Argument("orderId") UUID orderId,
        @ContextValue("tenantId") String tenantId) {

    return orderEventService.eventsForTenant(orderId, tenantId);
}
~~~

`tenantId` must be derived from a server-verified principal or token. Never take a tenant value from a GraphQL argument and use it directly to open a stream. Arguments supplied by the client only specify which resource they want to access; the service must verify that the principal has permission for that resource.

With WebSocket, distinguish the connection/session context from each GraphQL execution context. Never keep a single shared mutable `GraphQLContext` and overwrite the principal per operation; concurrent operations could read the wrong identity. Use per-execution context mechanisms and scope the security context to the proper lifecycle.

## 5. Checking permissions right at subscription registration

Before creating a publisher or subscribing to a broker, the server must verify whether the caller is allowed to subscribe to the requested resource.

Example service verifying order ownership:

~~~java
public Mono<Void> assertCanReadOrder(
        String principalName, UUID orderId) {

    return orderRepository.findOwnerAndTenant(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException()))
        .flatMap(order -> {
            boolean allowed = order.ownerName().equals(principalName);
            return allowed
                ? Mono.empty()
                : Mono.error(new AccessDeniedException("Access denied"));
        });
}
~~~

Resolver combining the permission check with the event source:

~~~java
@SubscriptionMapping
public Flux<OrderEvent> orderUpdated(
        @Argument("orderId") UUID orderId,
        Principal principal) {

    String username = principal.getName();

    return orderAuthorization.assertCanReadOrder(username, orderId)
        .thenMany(orderEventService.eventsForOrder(orderId));
}
~~~

`assertCanReadOrder` runs before the publisher emits events. This prevents the server from opening a subscription for an order the principal is not allowed to see.

Avoid merely filtering events after subscribing to a broad topic whenever possible. Event source subscriptions should be scoped by tenant/resource to avoid consuming irrelevant data and reduce leakage risks via timing, logs, or side channels.

## 6. Protecting subscriptions with Spring Security method security

Method security can be used to guard invocation of a subscription field:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

~~~java
@Controller
public class NotificationSubscriptionController {

    private final NotificationService notificationService;

    public NotificationSubscriptionController(
            NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @SubscriptionMapping
    @PreAuthorize("hasAuthority('notifications:read')")
    public Flux<Notification> notifications(Principal principal) {
        return notificationService.eventsForUser(principal.getName());
    }
}
~~~

`@PreAuthorize` checks the authority before the method executes. For Spring MVC/imperative applications, configure method security with `@EnableMethodSecurity`. For reactive applications, use the appropriate reactive method security configuration, such as `@EnableReactiveMethodSecurity`, and ensure `SecurityContext` is propagated in the Reactor Context.

Method security guards starting method execution, but it does not automatically enforce per-event policies across a long-lived publisher. If permissions can be revoked while a subscription is running, add event-time checks or a mechanism to terminate the stream when permissions change.

Do not use `@PreAuthorize` as a substitute for resource-specific authorization. `hasAuthority('notifications:read')` only confirms a coarse-grained authority; the service must still check which user/tenant a notification belongs to.

## 7. Authorization for each emitted event

Access permissions can change after a subscription begins. For example:

- The user is removed from a tenant.
- An order is reassigned to another owner.
- The login session is revoked.
- Permissions to view sensitive data are modified.
- The subscription is still running when the access token expires.

If permissions are checked only at subscribe time, the stream could continue sending data after access was lost. For sensitive data, check permissions per event or use a permission-monitoring mechanism to cancel the stream.

Example of filtering events by current permissions:

~~~java
@SubscriptionMapping
public Flux<OrderEvent> orderUpdated(
        @Argument("orderId") UUID orderId,
        Principal principal) {

    String username = principal.getName();

    return orderAuthorization.assertCanReadOrder(username, orderId)
        .thenMany(orderEventService.eventsForOrder(orderId)
            .filterWhen(event ->
                orderAuthorization.canReadEvent(username, event)));
}
~~~

`filterWhen` emits an event only when the authorization service returns `true`. Events that are no longer permitted are dropped from the stream. This prevents sending unauthorized payloads, though the stream may remain open and keep checking subsequent events.

If policy requires closing the subscription immediately upon revocation, combine the event stream with a publisher signaling permission changes or session invalidation, and cancel/complete the stream per policy. Do not merely drop events while keeping the subscription open indefinitely if that wastes resources or violates product contracts.

Per-event authorization has runtime cost. Choose an appropriate strategy:

| Strategy | When suitable | Limitations |
| --- | --- | --- |
| Single check at subscribe time | Low-sensitivity data, stable permissions during short streams | Does not reflect subsequent permission revocations |
| Per-event filtering | Permissions/resources can change and unauthorized payloads must be blocked | Increases calls to the authorization service |
| Monitoring permissions and cancelling stream | Need rapid revocation, long-lived subscriptions | Requires lifecycle management and revocation signals |
| Combine per-event check + revoke signal | Sensitive data, strict protection requirements | More complex, but tighter control |

## 8. Protecting tenants and topic subscriptions

Never let clients pick an arbitrary topic and receive events. For instance, a subscription taking `tenantId` as an argument can be abused if the service passes that ID straight to the broker:

~~~java
// Unsafe unless tenantId has been verified against principal.
return eventBroker.eventsForTenant(tenantId);
~~~

Instead, obtain the tenant scope from the authenticated principal and verify resource access:

~~~java
@SubscriptionMapping
public Flux<InvoiceEvent> invoiceChanged(
        @Argument("tenantId") String requestedTenantId,
        Principal principal) {

    return tenantAuthorization.assertCanAccess(
            principal.getName(), requestedTenantId)
        .thenMany(invoiceEventService.eventsForTenant(requestedTenantId));
}
~~~

In this example, `assertCanAccess` must verify membership/role from a trusted data source. In some systems, it is better to omit `tenantId` from arguments and derive the active tenant strictly from the principal. Only allow clients to select a tenant when the product genuinely supports tenant switching and the server enforces permissions.

If the event broker supports per-tenant topics or partitions, subscribe to the right partition after authorization succeeds. Never subscribe to a system-wide topic and rely solely on client-side filtering.

## 9. Field-level authorization for event payloads

Permission to subscribe to an event does not mean the user may view every field in the payload. For instance, a user might see order status but not shipping address or payment details.

Schema:

~~~graphql
type OrderEvent {
    orderId: ID!
    status: String!
    shippingAddress: String
    paymentReference: String
}
~~~

Sensitive fields can be guarded in a resolver:

~~~java
@Controller
public class OrderEventFieldController {

    @SchemaMapping(typeName = "OrderEvent", field = "paymentReference")
    @PreAuthorize("hasAuthority('orders:payment:read')")
    public String paymentReference(OrderEvent event) {
        return event.paymentReference();
    }
}
~~~

For reactive method security, use the appropriate reactive configuration if the method returns a publisher. If a field returns a synchronous value while resolved inside a reactive execution, still verify how the security context is propagated in your actual stack.

Another option is to omit sensitive data from the event DTO if the subscription does not need it. Smaller payloads reduce leakage risk, lower serialization overhead, and clarify the contract. When sensitive fields are included conditionally by permission, test both allowed and denied cases.

## 10. SecurityContext in reactive subscriptions

Subscriptions commonly rely on `Flux` and reactive execution. In reactive Spring Security, `SecurityContext` is stored in the Reactor Context rather than relying solely on `ThreadLocal`.

Therefore:

- Keep authorization logic inside the reactive chain.
- Avoid calling `block()` to retrieve the principal or permission check results.
- Never store `Authentication` in static fields or singleton mutable fields.
- Never assume a callback running on another thread can still see `ThreadLocal`.
- When bridging to `CompletableFuture` or manual executors, ensure context propagation or pass verified data explicitly.

Example keeping authorization inside the reactive chain:

~~~java
return notificationService.eventsForUser(principal.getName())
    .filterWhen(event ->
        authorizationService.canRead(principal, event));
~~~

`filterWhen` on `Flux` takes a predicate returning `Mono<Boolean>` and emits an event only when the predicate resolves to `true`. Do not call `subscribe()` inside a resolver to spin off a detached stream, because GraphQL needs to manage the returned publisher for execution, error handling, and subscription cancellation.

If a resolver accepts `Principal`, use the principal authenticated by Spring Security. Never read a username from an argument and treat it as the current identity.

## 11. Token expiration, logout, and permission revocation

A WebSocket connection can outlive a token. Define clear policies for these scenarios:

| Event | Recommended behavior |
| --- | --- |
| Token expired before a new operation | Reject the operation or require reconnection |
| Token expired while a subscription is running | Terminate the stream or require re-authentication per policy |
| User logs out | Cancel subscriptions tied to the session/principal if logout must take immediate effect |
| User removed from tenant | Stop emitting events belonging to that tenant |
| Role revoked | Re-apply policy on subsequent events/fields and cancel subscription if needed |
| Connection closed | Cancel the publisher and release broker listeners/resources |

One implementation approach is tracking links between principals/sessions and active subscriptions so revocation signals can be sent. Another approach uses a publisher broadcasting permission changes combined with the event stream. The exact design depends on broker infrastructure and revocation latency requirements.

Do not validate a token once when the connection opens and ignore expiry thereafter. If tokens carry mutable permission claims, decide whether to use a permission snapshot at subscribe time or read live permission state. For sensitive data, policy generally requires reflecting revocation within a reasonable time window.

## 12. Using WebSocketGraphQlInterceptor and WebGraphQlInterceptor

Spring for GraphQL provides web-layer interceptors:

- `WebGraphQlInterceptor` intercepts each `WebGraphQlRequest` before and after GraphQL execution.
- `WebSocketGraphQlInterceptor` adds WebSocket lifecycle hooks, such as connection initialization and connection close, while also participating in operation handling.

You can use interceptors to validate tokens from the connection initialization payload, set up the principal/context, and inspect per-operation metadata. However, an interceptor should not become the sole place holding all business authorization rules. Resource authorization checks should live in application services or policy components so REST, GraphQL, and message consumers can share them.

Responsibility matrix:

| Component | Responsibility |
| --- | --- |
| Spring Security handshake/filter | Authenticates HTTP connections and protects endpoints |
| `WebSocketGraphQlInterceptor` | Handles WebSocket connection init/close and metadata |
| `WebGraphQlInterceptor` | Enriches/validates context for each GraphQL request |
| `@PreAuthorize` / method security | Guards permission to invoke resolvers/methods |
| Authorization service | Checks permissions by user, tenant, and resource |
| Subscription publisher pipeline | Filters events, handles revocation and cancellation |
| `@SchemaMapping` or field resolver | Protects sensitive fields inside payloads |

If using a token in `connection_init`, never log the raw payload. Put only the verified principal and claims into context; avoid keeping the raw access token in `GraphQLContext` if resolvers do not need it.

## 13. Cancellation and releasing resources

Subscriptions can stay open for minutes or hours. When a client disconnects, cancels an operation, or loses permissions, the publisher must stop consuming events and release resources.

Example recording lifecycle:

~~~java
@SubscriptionMapping
public Flux<Notification> notifications(Principal principal) {
    String username = principal.getName();

    return notificationService.eventsForUser(username)
        .doFinally(signal ->
            log.debug("Notification subscription ended: user={}, signal={}",
                username, signal));
}
~~~

`doFinally` can record completion, errors, or cancellation. If a service registers a listener directly with a broker, ensure the publisher cleans up when the subscriber cancels—such as via `Flux.create`/`Flux.push` with cleanup callbacks or reactive broker APIs.

Do not spawn background subscriptions by calling `subscribe()` inside a controller. Doing so prevents GraphQL from managing the child publisher, backpressure, errors, or cancellation.

## 14. Testing subscription authorization

Testing regular queries and mutations is not enough to prove subscriptions are secure. You must test the handshake, connection initialization, operations, event streams, and cancellation. Spring for GraphQL provides `WebSocketGraphQlTester` for testing subscriptions over WebSocket; combine it with `StepVerifier` to verify emitted events.

Example stream test:

~~~java
Flux<OrderEventView> events = tester.document("""
        subscription($orderId: ID!) {
            orderUpdated(orderId: $orderId) {
                orderId
                status
            }
        }
        """)
    .variable("orderId", "order-01")
    .executeSubscription()
    .toFlux("orderUpdated", OrderEventView.class);

StepVerifier.create(events)
    .expectNextMatches(event ->
        event.orderId().equals("order-01"))
    .thenCancel()
    .verify();
~~~

This is an illustrative example; how you construct the tester and configure credentials depends on your test setup and Spring for GraphQL version. In real tests, use an appropriate principal/token and a test publisher capable of controlling emitted events.

Scenarios worth testing:

1. Connections without a token are rejected when the endpoint requires authentication.
2. Invalid tokens in handshake or connection initialization never produce a forged principal.
3. Principals with the required authority can subscribe.
4. Principals lacking the authority are rejected before registering a broker listener.
5. Users without access to an order/tenant receive no events.
6. Events are filtered out or the subscription is cancelled when permissions are revoked.
7. Sensitive fields remain protected even if the client includes them in the selection set.
8. Two users on the same endpoint never read across each other's data or caches.
9. Token expiration and logout behave according to policy.
10. Client cancellation or disconnection causes the publisher to release listeners.
11. Authorization errors do not reveal whether a resource exists.
12. WebSocket origin and credential handling match security configuration.

To test permission revocation, emit one valid event, change permissions in the test, and then emit a second event. Verify that the second event is not delivered and that the stream terminates if policy requires closing the subscription.

## 15. Common mistakes

| Mistake | Risk | Resolution |
| --- | --- | --- |
| Authenticating only the WebSocket handshake | New operations may use stale context/permissions | Authenticate and authorize per operation |
| Trusting `userId`/`tenantId` in connection payload | Client spoofs identity or tenant | Verify token and derive principal from server security context |
| Checking permissions only at subscribe time | Revoked permissions still let the stream deliver data | Check at event time or use revocation signals |
| Subscribing to a system-wide topic and filtering on client | Unauthorized data can leak | Scope topics/queries on the server by tenant/resource |
| Relying only on coarse-grained authorities | User can read the data type but does not own the specific resource | Check resource-level permissions in the service |
| Skipping field-level authorization | Event is valid, but sensitive fields leak | Protect nested fields or omit them from the payload |
| Using `ThreadLocal` in reactive flows | Principal/context gets lost or mixed across requests | Use Reactor Context, `GraphQLContext`, and explicit propagation |
| Ignoring token expiry | Long-lived connections stay active past expiry | Define re-authentication or termination policies |
| Calling `subscribe()` inside controller | GraphQL cannot manage cancellation or backpressure | Return the `Publisher` to GraphQL |
| Failing to clean up on disconnect | Listeners/broker consumers leak | Cancel event sources when the publisher cancels |
| Long-lived DataLoader caches without refresh | Child fields may return stale data or stale permissions | Set cache policies and invalidate/refresh alongside events |

## 16. Pre-production checklist for subscriptions

- WebSocket/SSE endpoints have proper authentication and origin policies.
- Tokens from handshake or `connection_init` are verified; self-declared client claims are never trusted.
- Each operation has a properly scoped principal and `GraphQLContext`.
- Subscription fields check both authorities and resource-level permissions.
- Event sources are scoped by tenant/resource on the server.
- Event-time authorization is applied whenever permissions can change.
- Sensitive fields in payloads have their own authorization.
- Token expiry, logout, and permission revocation have defined behavior.
- Publishers clean up on complete, error, or cancel.
- DataLoaders/caches are never shared across principals and enforce freshness policies.
- Logs never include raw tokens or sensitive connection payloads.
- Tests cover unauthorized access, cross-tenant isolation, revoked access, and cancellation.

## 17. Design principles

Authenticate connections at the proper transport boundary, while continuing to enforce permissions for every GraphQL operation. Before subscribing to an event source, verify that the principal has access to the requested resource and tenant. For sensitive streams or mutable permissions, check per event or listen for revocation signals to terminate subscriptions. Protect child fields of the payload as well, since permission to receive an event does not imply permission to read every field inside it.

Keep the security context aligned with execution and reactive lifecycles; avoid mutable singleton state or arbitrary `ThreadLocal` usage. Pass verified principals/tenants into services, scope topics on the server, and manage token expiry, cancellation, and caching. Use `WebSocketGraphQlTester` with `StepVerifier` to verify allowed data, denied data, and subscription lifecycle behavior.

In Spring for GraphQL, a subscription is a long-lived execution stream. Authorization must therefore protect the stream's entire lifecycle—from connection and registration through every emitted event, child field, and cancellation.
