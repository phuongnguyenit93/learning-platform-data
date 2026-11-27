# Protecting subscription connections

GraphQL subscriptions typically hold a connection open for a long time so the server can continuously push events to the client. With WebSockets, multiple subscriptions as well as queries and mutations can share a single connection. Therefore, security must manage the connection's identity, per-operation permissions, and permission to receive events throughout the stream's lifecycle.

Spring for GraphQL supports authentication during the **connection_init** message of the GraphQL over WebSocket protocol. Built-in authentication interceptors can extract a bearer token from the payload, authenticate it, and propagate the **SecurityContext** to subsequent GraphQL operations on the same WebSocket session. This lesson focuses on securing connections, restricting permissions on running subscriptions, and handling expired tokens or revoked user permissions.

## 1. Why do subscriptions need connection-level protection?

An HTTP query typically ends once the server returns a response. A WebSocket connection has a longer lifecycle: the client opens a connection, sends an initialization message, and can then start multiple subscriptions. Each subscription keeps emitting events until the client cancels, the publisher completes, an error occurs, or the connection closes.

Example schema for tracking order status:

~~~graphql
type Query {
    order(id: ID!): Order
}

type Subscription {
    orderUpdates(orderId: ID!): OrderUpdate!
}

type Order {
    id: ID!
    status: String!
}

type OrderUpdate {
    orderId: ID!
    status: String!
    changedAt: String!
}
~~~

A client may open a subscription for order order-42 and hold the connection open for many minutes. If the server only authenticates during the HTTP handshake without binding identity to subsequent GraphQL operations, resolvers may not know who is requesting data. If the connection authenticated once but user permissions change while the stream is active, subsequent events risk being sent to someone no longer authorized to view them.

Three layers must be distinguished:

- **Connection authentication:** establishing client identity when setting up or initializing the WebSocket session.
- **Operation authorization:** verifying whether the user has permission to start the subscription or invoke specific fields.
- **Event authorization:** verifying whether each event's data may still be sent to the subscriber throughout the stream's lifetime, if business rules require immediate permission revocation.

## 2. Two phases of GraphQL over WebSocket

GraphQL over WebSocket uses the graphql-ws protocol with messages managing connections and operations. Spring for GraphQL supports this protocol through GraphQlWebSocketHandler.

Basic lifecycle:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant H as HTTP/WebSocket handshake
    participant S as Spring GraphQL
    participant A as Authentication
    participant R as Resolver/Publisher

    C->>H: HTTP Upgrade request
    H-->>C: 101 Switching Protocols
    C->>S: connection_init + payload
    S->>A: Extract and authenticate credentials
    A-->>S: Authenticated SecurityContext
    S-->>C: connection_ack
    C->>S: subscribe + GraphQL operation
    S->>R: Execute subscription resolver
    R-->>C: Event 1, Event 2, ...
    C->>S: complete / unsubscribe
    S->>R: Cancel publisher
    C->>H: Close WebSocket
~~~

There are two distinct points in time:

1. **HTTP handshake:** the browser requests upgrading HTTP to WebSocket. The server can inspect Origin, session cookies, or credentials sent in the handshake.
2. **GraphQL connection initialization:** after the WebSocket opens, the client sends connection_init. This message's payload can contain a bearer token. The server authenticates the payload before accepting GraphQL operations on the connection.

If using a bearer token in connection_init, the HTTP handshake may not yet carry a user identity. Therefore, you must configure a connection authentication interceptor and disallow operations from running before initialization is accepted.

## 3. Enabling the WebSocket endpoint in Spring Boot

Spring Boot does not automatically enable the GraphQL WebSocket endpoint in every configuration. You can declare a dedicated path using spring.graphql.websocket.path:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql-ws
      connection-init-timeout: 10s
      keep-alive: 30s
~~~

Meaning:

| Property | Purpose |
| --- | --- |
| spring.graphql.websocket.path | Enables the GraphQL WebSocket endpoint at the specified path |
| spring.graphql.websocket.connection-init-timeout | Maximum wait time for the first connection_init message; defaults to 60s |
| spring.graphql.websocket.keep-alive | Maximum idle interval before the server sends a keep-alive ping |

Using a separate path like /graphql-ws distinguishes the WebSocket handshake from the HTTP GraphQL endpoint /graphql. This is especially useful when configuring Spring Security: HTTP requests and WebSocket handshakes may need different rules.

Keep-alive only checks whether the connection is still alive using ping/pong. It does not validate that a token is still valid, does not extend a login session, and does not replace authorization.

## 4. Sending bearer tokens in connection_init

For browser-based applications, the standard WebSocket API does not allow JavaScript to arbitrarily attach an Authorization header to the handshake like fetch does. The GraphQL over WebSocket protocol provides the connection_init payload for clients to send initialization metadata, commonly used for credentials.

Example message:

~~~json
{
  "type": "connection_init",
  "payload": {
    "Authorization": "Bearer eyJhbGciOi..."
  }
}
~~~

The server responds with connection_ack when initialization is accepted. Only then does the client send subscribe operations.

With the JavaScript graphql-ws library, you can configure connectionParams:

~~~javascript
import { createClient } from "graphql-ws";

const client = createClient({
  url: "wss://api.example.com/graphql-ws",
  connectionParams: async () => {
    const accessToken = await getAccessToken();

    return {
      Authorization: "Bearer " + accessToken
    };
  }
});
~~~

connectionParams is used to build the connection_init payload. If the client reconnects, the callback can fetch a fresh access token for the new connection. Never put tokens in query strings because URLs frequently appear in access logs, browser history, proxy logs, and monitoring systems.

Always use wss:// in production to encrypt tokens and subscription data in transit.

## 5. Built-in AuthenticationWebSocketInterceptor

Spring for GraphQL provides two classes named AuthenticationWebSocketInterceptor:

- org.springframework.graphql.server.webmvc.AuthenticationWebSocketInterceptor for Spring MVC.
- org.springframework.graphql.server.webflux.AuthenticationWebSocketInterceptor for Spring WebFlux.

Both extend AbstractAuthenticationWebSocketInterceptor. They extract credentials from the connection_init payload, invoke the authentication manager, store the authentication in WebSocket session attributes, and propagate the SecurityContext to subsequent GraphQL requests on the connection.

BearerTokenAuthenticationExtractor is a built-in extractor for retrieving bearer tokens. The default constructor uses the Authorization key in the payload:

~~~java
new BearerTokenAuthenticationExtractor()
~~~

This fits when clients send Authorization: Bearer ... in connection_init. If the application uses a different payload structure, you can implement a custom AuthenticationExtractor.

## 6. Registering the interceptor for Spring MVC

For the servlet stack, register the WebMVC interceptor as a bean. The example below assumes the application already has a JwtDecoder configured via issuer URI and uses JWT bearer tokens:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

Configuring the interceptor:

~~~java
package com.example.graphql.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.WebSocketGraphQlInterceptor;
import org.springframework.graphql.server.support.BearerTokenAuthenticationExtractor;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.jwt.JwtDecoder;

@Configuration
public class GraphQlWebSocketSecurityConfiguration {

    @Bean
    AuthenticationManager webSocketAuthenticationManager(JwtDecoder jwtDecoder) {
        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(jwtDecoder);

        return new ProviderManager(provider);
    }

    @Bean
    WebSocketGraphQlInterceptor webSocketAuthenticationInterceptor(
            AuthenticationManager webSocketAuthenticationManager) {

        return new org.springframework.graphql.server.webmvc.AuthenticationWebSocketInterceptor(
            new BearerTokenAuthenticationExtractor(),
            webSocketAuthenticationManager
        );
    }
}
~~~

JwtAuthenticationProvider verifies the bearer token with JwtDecoder and produces an authenticated Authentication. In systems using custom claims or a dedicated authority converter, configure the same converter on this provider so authorities in the WebSocket session remain consistent with the HTTP resource server.

Do not register both WebMVC and WebFlux interceptors simultaneously. Choose the right class for your application stack. The WebSocketGraphQlInterceptor bean is used by Spring Boot in the interception chain of the GraphQL WebSocket endpoint.

## 7. Registering the interceptor for Spring WebFlux

With WebFlux, the constructor accepts ReactiveAuthenticationManager instead of AuthenticationManager. Example:

~~~java
package com.example.graphql.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.WebSocketGraphQlInterceptor;
import org.springframework.graphql.server.support.BearerTokenAuthenticationExtractor;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;

@Configuration
public class GraphQlWebSocketSecurityConfiguration {

    @Bean
    ReactiveAuthenticationManager webSocketAuthenticationManager(
            ReactiveJwtDecoder jwtDecoder) {
        return new JwtReactiveAuthenticationManager(jwtDecoder);
    }

    @Bean
    WebSocketGraphQlInterceptor webSocketAuthenticationInterceptor(
            ReactiveAuthenticationManager webSocketAuthenticationManager) {

        return new org.springframework.graphql.server.webflux.AuthenticationWebSocketInterceptor(
            new BearerTokenAuthenticationExtractor(),
            webSocketAuthenticationManager
        );
    }
}
~~~

JwtReactiveAuthenticationManager validates tokens in a reactive flow. Use ReactiveJwtDecoder and the corresponding issuer/JWK configuration. Never mix a synchronous Servlet authentication manager with the WebFlux interceptor.

## 8. Protecting the HTTP handshake and connection_init

When using a bearer token in connection_init, you can allow the HTTP handshake to the WebSocket path to pass through the filter chain and let the interceptor authenticate the payload. Use a dedicated path so you do not accidentally open the HTTP GraphQL endpoint:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/graphql-ws").permitAll()
            .requestMatchers("/graphql").authenticated()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
        .build();
}
~~~

permitAll() here only lets the WebSocket upgrade request reach the handler. It grants no identity and does not replace authentication in connection_init. The interceptor must reject payloads that are missing or carry invalid tokens; clients may only send subscriptions after the server accepts connection initialization.

If using cookie/session authentication, authenticate right at the HTTP handshake and require a valid session for the WebSocket endpoint. Do not apply the bearer-payload permitAll() setup to a cookie model without redesigning the security boundary.

Keep CSRF protection appropriate for cookie/session mechanisms on HTTP endpoints. CSRF filters and CORS do not replace Origin validation on the WebSocket handshake.

## 9. How is Authentication propagated to subscriptions?

Once connection_init is authenticated, AuthenticationWebSocketInterceptor stores the authentication in WebSocket session attributes. For each subsequent GraphQL request on that session, the interceptor restores and propagates the SecurityContext into the Reactor context so resolvers and services can use it.

Example resolver accepting principal:

~~~java
import java.security.Principal;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class OrderSubscriptionController {

    private final OrderService orderService;

    public OrderSubscriptionController(OrderService orderService) {
        this.orderService = orderService;
    }

    @SubscriptionMapping
    public Flux<OrderUpdate> orderUpdates(
            @Argument("orderId") String orderId,
            Principal principal) {

        return orderService.updatesVisibleTo(
            orderId,
            principal.getName()
        );
    }
}
~~~

Principal represents the authenticated user on the connection. The resolver does not need to accept a userId from the client and trust it to decide who may view the stream.

All operations on the same WebSocket session share the connection's identity. Therefore, never reuse one WebSocket client instance across different logged-in users. When switching accounts, close the old connection and open a new connection with the new user's credentials.

## 10. Authorization at start and during the running stream

@PreAuthorize or permission checks in services can guard starting a subscription:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Flux<OrderUpdate> updatesVisibleTo(String orderId, String username) {
    return orderRepository.findUpdatesVisibleTo(orderId, username);
}
~~~

However, a subscription resolver is typically called once when the client starts the operation. If a user's permissions are revoked afterward, method security annotations do not automatically re-run for every emitted event.

If policy requires permissions to be checked continuously, filter or verify within the event stream:

~~~java
@SubscriptionMapping
public Flux<OrderUpdate> orderUpdates(
        @Argument("orderId") String orderId,
        Principal principal) {

    return orderService.updatesFor(orderId)
        .filterWhen(update ->
            authorizationService.canReadUpdate(principal.getName(), update)
        );
}
~~~

Another approach is creating a publisher that only emits events within the principal's tenant/owner scope, or terminating the stream when an account is locked or permissions are revoked. Choose a strategy based on data sensitivity and revocation latency requirements.

Never assume a one-time permission check when opening the connection protects every event forever. A long-lived connection can outlive the initial access token, login session, or granted permissions.

## 11. Token expiration and credential refresh

The connection_init message is sent only at the beginning of a WebSocket session. The built-in authentication interceptor validates the token at initialization and propagates the authenticated SecurityContext to subsequent requests.

This leads to several design considerations:

- Token expiration after the connection is authenticated does not automatically stop all running subscriptions immediately.
- Refreshing the access token on the client does not automatically re-send connection_init on an already open session.
- A new connection can send a new token in connection_init.
- If immediate permission revocation is required, you must implement permission re-evaluation, session revocation, or publisher termination.

A common strategy is using short-lived access tokens, tracking expiration timestamps, and proactively closing/reconnecting the WebSocket with a fresh token. For systems requiring instant revocation, combine this with a session registry or permission-revocation events so the server can close the user's connections or cancel their subscriptions.

Do not treat PING/PONG keep-alive as a token refresh mechanism. Ping only detects whether the connection is still active.

## 12. Origin validation and Cross-Site WebSocket Hijacking

Browsers automatically send matching cookies when initiating a WebSocket handshake. If an application uses cookie sessions and accepts WebSockets from any Origin, a malicious page can trick a logged-in user's browser into opening a connection to the server and executing GraphQL operations using the victim's session. This is Cross-Site WebSocket Hijacking (CSWSH).

Origin validation must be configured at the WebSocket handshake:

- Allow only valid frontend origins.
- Never use wildcard * when connections use cookies or user credentials.
- Never treat HTTP CORS as a protection mechanism for WebSockets.
- Use TLS wss://.
- Connection authentication and per-operation authorization still must be enforced separately.

Origin is a browser-origin control signal, not an identity. Non-browser clients can forge Origin headers, so never use Origin as a replacement for authentication.

### CVE-2026-41700 patch note

Spring for GraphQL disclosed CVE-2026-41700 regarding Cross-Site WebSocket Hijacking. Applications are affected when WebSocket transport is enabled, cookie-based session authentication is used, and no Origin check is configured at the WebSocket/Spring Security level.

Affected OSS version ranges include:

- 1.0.0 through 1.0.6.
- 1.3.0 through 1.3.8.
- 1.4.0 through 1.4.5.
- 2.0.0 through 2.0.3.

Patched OSS versions include 1.4.6 and 2.0.4 on their respective branches. Prefer a supported version that already includes the patch. Older end-of-life versions may no longer receive public OSS patches.

The patch applies a default same-origin policy for the GraphQL WebSocket handshake. If the application genuinely requires cross-origin access, configure an explicit origin allow-list only. Never open to all origins just to work around connection errors. Consult the official advisory before deploying or upgrading.

## 13. Connection and resource limits

A WebSocket session can hold multiple concurrent subscriptions. A single client can exhaust CPU, memory, queues, and broker connections if the server does not impose limits.

You should control:

- Maximum WebSocket connections at the server, reverse proxy, or connector.
- Maximum WebSocket message buffer size.
- connection_init timeout.
- Maximum concurrent subscriptions per session.
- Connections or subscriptions per user/tenant.
- Event emission rate, queue size, and backpressure.
- Maximum connection lifetime if security policy requires periodic reconnection.

Spring GraphQL lets you limit maxSubscriptionsPerSession when building GraphQlWebSocketHandler. By default there is no limit; once the configured threshold is reached, the session is closed. Message buffer size and maximum connection counts belong to the underlying server/connector configuration, not just a single GraphQL property.

Never allow clients to subscribe with overly broad filters or open thousands of unbounded streams. Combine query cost/depth limits, rate limits, pagination, and tenant authorization.

## 14. Monitoring connection lifecycle and cancellation

WebSocketGraphQlInterceptor extends WebGraphQlInterceptor and provides callbacks for connection lifecycle events:

- handleConnectionInitialization(...): processes the connection_init payload.
- handleCancelledSubscription(...): receives notification when a client cancels a subscription.
- handleConnectionClosed(...): invoked when the WebSocket session closes.
- intercept(...): intercepts each GraphQL request on the connection.

The handleCancelledSubscription callback is invoked when the client sends complete; the underlying subscription publisher is cancelled automatically. This callback can be used for audit logging or extra resource cleanup. handleConnectionClosed is suited to releasing session-scoped state.

Within an interceptor chain, there can be at most one WebSocketGraphQlInterceptor. If you need both authentication and lifecycle monitoring, combine the logic into one interceptor or use standard WebGraphQlInterceptors for tasks that do not require WebSocket-specific callbacks.

Never write raw tokens, entire connection_init payloads, or cookies to logs. You can log session IDs, normalized user IDs, active subscription counts, open/close timestamps, and termination reasons per audit policy.

## 15. Distinguishing WebSocket, SSE, and RSocket

Not all GraphQL subscriptions use the same connection authentication mechanism:

| Transport | Typical authentication | Scope |
| --- | --- | --- |
| WebSocket | HTTP handshake/session or token in connection_init | One identity bound to the WebSocket session, shared across multiple operations |
| SSE | HTTP security filter chain and credentials on the stream-opening request | Each stream is a separate HTTP request |
| RSocket | Authentication via RSocket setup/metadata and RSocket security | RSocket connection/session and requests per configuration |

SSE does not use connection_init; protect the stream-creating HTTP request with Spring Security. RSocket does not use the GraphQL WebSocket protocol, so AuthenticationWebSocketInterceptor does not apply to RSocket. Choose the interceptor and security mechanism matching the active transport.

## 16. Testing subscription connection security

Tests must verify initial authentication, operation permissions, and long-lived stream behavior.

You can use WebSocketGraphQlTester to test against a real WebSocket server or a test environment supporting WebSockets:

~~~java
import java.util.Map;

import org.springframework.graphql.client.WebSocketGraphQlClientInterceptor;
import org.springframework.graphql.test.tester.WebSocketGraphQlTester;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import reactor.core.publisher.Mono;

WebSocketGraphQlTester tester =
    WebSocketGraphQlTester.builder(
            "ws://localhost:8080/graphql-ws",
            new ReactorNettyWebSocketClient()
        )
        .interceptor(new WebSocketGraphQlClientInterceptor() {
            @Override
            public Mono<Object> connectionInitPayload() {
                return Mono.just(Map.of(
                    "Authorization", "Bearer " + accessToken
                ));
            }

            @Override
            public Mono<Void> handleConnectionAck(Map<String, Object> payload) {
                return Mono.empty();
            }
        })
        .build();
~~~

The example assumes accessToken is a valid test JWT and the server has registered the corresponding AuthenticationWebSocketInterceptor. In real tests, never hardcode production tokens; use test tokens or a test identity provider.

Scenarios to include:

1. Valid token: connection is acknowledged and subscription receives events.
2. Missing token: connection initialization is rejected and no operations execute.
3. Invalid signature or expired token: no successful connection_ack is received.
4. User lacks scope: connection may authenticate, yet the operation is denied.
5. User loses permissions while stream is running: subsequent events are filtered or the subscription terminates per policy.
6. Client sends complete: publisher is cancelled and dedicated resources are cleaned up.
7. WebSocket handshake from disallowed Origin: server rejects the handshake.
8. A session reaches the subscription limit: server closes the session or rejects per configuration.
9. Two different users: connections and SecurityContexts are not shared.
10. Token refresh: client reconnects and sends the new token in connection initialization.

Use StepVerifier to test events and cancellation at the publisher layer; use WebSocketGraphQlTester or transport integration tests to verify protocol handling, authentication handshake, and real cleanup. Testing a service Flux alone does not prove the WebSocket handler propagated the security context properly.

## 17. Common issues

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| WebSocket opens yet subscribe is rejected | connection_init not sent or payload lacks token | Check client connection parameters |
| HTTP queries are authenticated yet WebSocket subscriptions are anonymous | Token only sent in HTTP header, not passed in connection initialization | Use AuthenticationWebSocketInterceptor or cookie/session handshake |
| Valid token yet authentication interceptor rejects it | AuthenticationManager does not support the bearer token type produced by extractor | Configure a provider supporting BearerTokenAuthenticationToken |
| Principal is missing in resolver | SecurityContext not propagated into WebSocket requests | Check matching MVC/WebFlux interceptor and bean registration |
| User switches account yet still receives old events | WebSocket client reuses a session authenticated as the previous user | Close the session and create a new connection |
| Token expires yet subscription keeps running | Authentication was validated at connection init and context remains on the session | Reconnect, check permissions inside the stream, or proactively revoke the session |
| Cookie-auth WebSocket hit by CSWSH | Origin not restricted or vulnerable version | Upgrade to patched version and configure an Origin allow-list |
| Single client opens too many subscriptions | No subscription/connection limits | Set limits per session, user, and infrastructure |
| Cleanup fails to run when client disconnects | Cancellation or connection-close lifecycle not handled | Use publisher cleanup and appropriate lifecycle callbacks |

## 18. Implementation checklist

- Is the GraphQL WebSocket endpoint enabled on a dedicated path and exposed only for required transports?
- Do clients send credentials in the HTTP handshake or connection_init following one consistent model?
- Is the interceptor matching the MVC/WebFlux stack registered?
- Does AuthenticationManager verify token, issuer, signature, and expiration?
- Are operations processed only after connection initialization is accepted?
- Is Principal/SecurityContext propagated to resolvers and services?
- Is authorization checked when starting a subscription and inside the stream if immediate revocation is required?
- Is there a clear close/reconnect strategy for token refresh or user switching?
- Does WebSocket Origin allow only valid frontend origins, especially when using cookies/sessions?
- Is Spring for GraphQL on a version patched for CVE-2026-41700?
- Are connection counts, message sizes, and concurrent subscriptions capped?
- Are connection open/close, cancellations, and authentication failures audited without logging tokens?
- Do integration tests cover valid tokens, invalid tokens, insufficient permissions, disallowed Origins, and cancellation?

Protecting subscription connections requires managing both the WebSocket session's identity and data access permissions throughout the stream lifecycle. Spring for GraphQL provides AuthenticationWebSocketInterceptor to validate tokens in connection_init and propagate SecurityContext to subsequent operations. Applications still must enforce authorization, handle expired tokens and permission revocation, limit resources, and protect handshake Origins. Combining these layers keeps subscriptions secure even when connections are long-lived and carry multiple concurrent operations.

## References

- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — WebSocket Authentication API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/support/AbstractAuthenticationWebSocketInterceptor.html)
- [Spring for GraphQL — WebSocket Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Security Advisory — CVE-2026-41700](https://spring.io/security/cve-2026-41700)
- [Spring for GraphQL Examples — WebSocket Authentication](https://github.com/spring-projects/spring-graphql-examples)
