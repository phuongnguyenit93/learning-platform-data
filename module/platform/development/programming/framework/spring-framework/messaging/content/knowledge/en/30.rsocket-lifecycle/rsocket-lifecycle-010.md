# Metadata Authentication and Route Authorization with Spring Security

## 1. Authentication and Authorization in RSocket

An RSocket request can carry a route, a security token, and data within the same `Payload`. Spring Security uses RSocket metadata extensions to identify the sender and decide which routes that principal is allowed to invoke.

Two concepts to separate:

- **Authentication** answers: who is the request coming from? For instance, does the token have a valid signature, is it unexpired, and which principal does it represent?
- **Authorization** answers: is that principal permitted to execute this request? For instance, only users with the `SCOPE_orders.write` authority may invoke the order-creation route.

RSocket has long-lived connections and supports multiple concurrent requests over the same connection. Therefore, choosing when to authenticate is critical. If a connection belongs to a single user, authenticating during connection setup may be appropriate. If a connection is shared among many end users, authenticate per request so each request carries its own identity.

Spring Security provides a dedicated integration layer for RSocket. It does not protect RSocket via Servlet filter chains or HTTP's `SecurityFilterChain`. The security flow is installed on `SocketAcceptor` and processes each `PayloadExchange` using interceptors.

## 2. Required Dependencies

For a Spring Boot application using Gradle that requires JWT authentication, the main dependencies can be declared as follows:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.security:spring-security-rsocket")
    implementation("org.springframework.security:spring-security-messaging")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
}
```

Spring Boot dependency management handles compatible versions. With Spring Boot 3.3.x, Spring Security belongs to the 6.3.x line; do not pick different Spring Security versions for individual modules manually.

Roles of the dependencies:

- `spring-security-rsocket` provides security interceptors and DSL for RSocket.
- `spring-security-messaging` provides security integration for Spring Messaging.
- `spring-boot-starter-security` provides foundational components such as authentication, authorization, and password encoding.
- `spring-boot-starter-oauth2-resource-server` provides JWT access token validation and `ReactiveJwtDecoder`.

If the application only uses Simple Authentication with username/password, OAuth2 Resource Server is not needed solely for RSocket. If using JWT as in the main example below, the Resource Server dependency is required.

## 3. Security Processing Architecture

In Spring Security RSocket, the main components collaborate as follows:

```text
RSocketRequester
    |
    | route + authentication metadata + data
    v
RSocket transport
    |
    v
SecuritySocketAcceptorInterceptor
    |
    v
PayloadSocketAcceptorInterceptor
    |
    +--> AuthenticationPayloadInterceptor
    |       |
    |       +--> ReactiveAuthenticationManager
    |               |
    |               +--> ReactiveJwtDecoder / identity provider
    |
    +--> AuthorizationPayloadInterceptor
            |
            +--> ReactiveAuthorizationManager
                    |
                    +--> route and authority
    |
    v
RSocketMessageHandler
    |
    v
@MessageMapping handler
```

`@EnableRSocketSecurity` enables Spring Security configuration for RSocket. `RSocketSecurity` is the DSL for declaring authentication mechanisms and authorization rules. When built, Spring Security creates `PayloadSocketAcceptorInterceptor` and integrates it into the RSocket server via `SecuritySocketAcceptorInterceptor`.

In a Spring Boot application with an RSocket server and appropriate dependencies, Spring Boot auto-configuration registers the security interceptor on the server. If creating an RSocket server manually outside auto-configuration, you must attach `SecuritySocketAcceptorInterceptor` to `SocketAcceptor` yourself.

`RSocketMessageHandler` supports Composite Metadata and Routing Metadata by default. Thus, the route and token can coexist in one metadata payload according to the RSocket extensions.

## 4. Choosing Authentication Timing: SETUP or Per Request?

RSocket supports authentication at two primary points:

| Timing | How Metadata Is Sent | When Appropriate |
|---|---|---|
| SETUP | `setupMetadata(value, mimeType)` | One connection belongs to one principal for the connection's entire lifecycle |
| Request | `metadata(value, mimeType)` | One connection is shared, and each request may belong to a different user |

### Authenticating at SETUP

The requester sends credentials in the `SETUP` frame's metadata. The responder authenticates when the connection is established. Subsequent requests can use the security context bound to that connection.

This approach suits a device or a client logging in with one account and using a dedicated connection. When credentials are invalid, the server can reject the connection right at setup.

Do not use this model for a connection shared across many end users if each request requires per-user authorization. Otherwise, the identity authenticated at SETUP only represents the connection and does not change dynamically per user sending requests.

### Authenticating on Each Request

The requester attaches credentials to the metadata of each request. A single connection can serve requests from multiple users, provided each request carries the corresponding user's token.

This is the right model when a backend or gateway opens a shared RSocket connection to a downstream service. Requests from Alice and Bob are still authenticated independently despite traveling over the same connection.

### Both Can Be Combined

A system can authenticate the client/service at SETUP and authenticate the end user on each request. For example, credentials at SETUP prove the connection comes from an authorized backend; a JWT on the request proves the end user is authorized to perform the business operation.

If combining both, clearly distinguish which authorities belong to the service and which belong to the end user. Never let service permissions accidentally substitute for user permission checks.

## 5. Configuring JWT Authentication and Route Authorization

JWT is a good fit when the application already has an identity provider issuing access tokens. The client sends the JWT using the Bearer Token Authentication Metadata Extension. Spring Security decodes the token, verifies its signature and token conditions via `ReactiveJwtDecoder`, and builds an `Authentication` for authorization decisions.

Server configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfig {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        rsocket
            .authorizePayload(authorize -> authorize
                .setup().permitAll()

                .route("admin.*").hasRole("ADMIN")

                .route("orders.create")
                    .hasAuthority("SCOPE_orders.write")

                .route("orders.read.*")
                    .hasAuthority("SCOPE_orders.read")

                .anyRequest().authenticated()
                .anyExchange().authenticated()
            )
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        return NimbusReactiveJwtDecoder
                .withIssuerLocation("https://idp.example.com/issuer")
                .build();
    }
}
```

Replace `https://idp.example.com/issuer` with your actual identity provider's issuer URI. `NimbusReactiveJwtDecoder.withIssuerLocation(...)` uses the issuer's metadata discovery to locate verification keys. If the identity provider does not support discovery, configure an appropriate JWK Set URI instead.

You should also validate the token's audience for the API the server provides. Valid signature and matching issuer are insufficient if the token was issued for a different service. In production systems, configure validators for audience and required business claims.

### Understanding Each Authorization Rule

- `setup().permitAll()` allows establishing a connection without a JWT in SETUP. This is intentional when the application authenticates JWTs on each request.
- `route("admin.*").hasRole("ADMIN")` requires the `ROLE_ADMIN` authority for routes matching the `admin.*` pattern.
- `route("orders.create").hasAuthority("SCOPE_orders.write")` requires the exact `SCOPE_orders.write` authority.
- `route("orders.read.*").hasAuthority("SCOPE_orders.read")` applies read permission to sub-routes under `orders.read`.
- `anyRequest().authenticated()` requires every remaining request to have an authenticated principal.
- `anyExchange().authenticated()` requires authentication for remaining exchanges outside requests, such as metadata pushes.

Rules are evaluated in declaration order; the first matching rule wins. Therefore, place specific routes before general rules like `anyRequest()`. If you place `anyRequest()` ahead of routes needing specific permissions, the later route rules will never be evaluated.

`anyRequest()` applies to payload exchanges that are requests. `anyExchange()` is broader and covers non-request exchanges as well. In the example, SETUP is explicitly permitted; remaining requests require authentication, and other exchanges also require authentication. Even if the application does not use metadata pushes, this rule keeps an explicit control policy for non-request exchanges.

Note that `anyRequest().authenticated()` allows any authenticated principal to invoke routes without dedicated rules. If you require a default-deny policy, replace this fallback with `anyRequest().denyAll()` and explicitly declare every allowed route.

### Distinguishing `hasRole` and `hasAuthority`

`hasRole("ADMIN")` automatically prepends `ROLE_`, so it checks for `ROLE_ADMIN`.

`hasAuthority("SCOPE_orders.write")` compares the exact authority string passed in. Spring Security Resource Server by default maps JWT scopes into authorities prefixed with `SCOPE_`.

Example JWT payload with claims:

```json
{
  "iss": "https://idp.example.com/issuer",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write"
}
```

Once the token is validated, those scopes are typically mapped to:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Hence Alice can invoke `orders.create` if the token is valid and contains the `orders.write` scope. A valid token lacking the scope is still rejected at the authorization step.

## 6. Client Sending JWT in Composite Metadata

Spring Framework uses Composite Metadata by default for RSocket. The client can send the route and Bearer token as two separate metadata entries in the same request.

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

public class OrderRSocketClient {

    private static final MimeType BEARER_AUTHENTICATION =
            MimeTypeUtils.parseMimeType(
                "message/x.rsocket.authentication.bearer.v0");

    public Mono<OrderReceipt> createOrder(
            RSocketRequester requester,
            String accessToken,
            CreateOrder command) {

        return requester
                .route("orders.create")
                .metadata(accessToken, BEARER_AUTHENTICATION)
                .data(command)
                .retrieveMono(OrderReceipt.class);
    }
}
```

In the example, `requester` is an established RSocket connection; `CreateOrder` and `OrderReceipt` are application DTOs.

1. `route("orders.create")` creates Routing Metadata so the server identifies the handler.
2. `metadata(accessToken, BEARER_AUTHENTICATION)` adds the Bearer token to the request metadata.
3. `data(command)` encodes the business data in the data section.
4. `retrieveMono(OrderReceipt.class)` decodes the response into the expected result type.

MIME type `message/x.rsocket.authentication.bearer.v0` is the MIME type of the Bearer Token Authentication Metadata Extension. When `.jwt(Customizer.withDefaults())` is used, Spring Security auto-configures a converter to extract the token from this extension and convert it into an authentication request.

There is no need to craft an HTTP-style `Authorization` header or concatenate the token into data. Use the proper metadata extension so both sides understand the same protocol.

If you want to send additional application metadata such as tenant ID or correlation ID, call `.metadata(value, mimeType)` with the corresponding MIME type. Those values are purely client-supplied data. They do not by themselves prove tenant, role, or principal access rights. The server must verify them against the authenticated identity and stored policies.

## 7. Username/Password Authentication at SETUP with Simple Authentication

If one connection represents a single user, you can use the Simple Authentication Metadata Extension. The client sends `UsernamePasswordMetadata` in SETUP and registers `SimpleAuthenticationEncoder` to encode it in the proper format.

Server security configuration example:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {

    rsocket
        .authorizePayload(authorize -> authorize
            .setup().authenticated()
            .route("admin.*").hasRole("ADMIN")
            .anyRequest().authenticated()
            .anyExchange().authenticated()
        )
        .simpleAuthentication(Customizer.withDefaults());

    return rsocket.build();
}
```

The server needs a `ReactiveAuthenticationManager` or appropriate user service configuration to verify username/password. A simple demo may use `MapReactiveUserDetailsService` in a learning environment; real applications should use an appropriate user store or identity provider and a secure `PasswordEncoder`.

Client sending credentials when connecting:

```java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

public class SecureRSocketConnection {

    public Mono<RSocketRequester> connect(
            RSocketRequester.Builder builder,
            String host,
            int port,
            String username,
            String password) {

        MimeType simpleAuthenticationMimeType =
                MimeTypeUtils.parseMimeType(
                    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

        UsernamePasswordMetadata credentials =
                new UsernamePasswordMetadata(username, password);

        return builder
                .setupMetadata(credentials, simpleAuthenticationMimeType)
                .rsocketStrategies(strategies ->
                        strategies.encoder(new SimpleAuthenticationEncoder()))
                .connectTcp(host, port);
    }
}
```

`SimpleAuthenticationEncoder` encodes `UsernamePasswordMetadata` per the Simple Authentication extension. The server uses the configured authentication mechanism to verify credentials.

Simple Authentication transmits username/password in metadata; the extension itself does not encrypt secrets. When using it, protect the transport with TLS to guarantee confidentiality and authenticity in transit. Do not log credentials and do not use sample users/passwords in production.

This configuration is an alternative to the JWT example in the previous section. Do not register two interceptor beans for the same purpose without a clear design for combining authentication mechanisms.

## 8. Combining Route Authorization with Method Security

Route authorization protects the RSocket boundary: which principals are allowed to call a route. Method security can add rules at the service layer so the same business logic stays protected even when invoked through another path.

Example business DTOs:

```java
public record CreateOrder(String orderId) {
}

public record OrderReceipt(String orderId, String status) {
}
```

Service using reactive method security:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public Mono<OrderReceipt> create(CreateOrder command) {
        // Execute order creation business logic.
        return Mono.just(new OrderReceipt(command.orderId(), "ACCEPTED"));
    }
}
```

To enable it, declare `@EnableReactiveMethodSecurity` in application configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfig {
}
```

Reactive method security suits methods returning `Mono` or `Flux`. You can use route authorization to reject invalid requests early, and then use `@PreAuthorize` on the service to guard critical business logic. Keep the rules consistent so a route does not permit a request only for the service to enforce an unexpected policy.

## 9. Attaching the Interceptor Without Spring Boot Auto-Configuration

When using Spring Boot with an auto-configured RSocket server and the right dependencies, Spring Boot registers the security interceptor automatically. When building an RSocket server manually, attach `SecuritySocketAcceptorInterceptor` to the server.

Example using `RSocketServerCustomizer`:

```java
import org.springframework.boot.rsocket.server.RSocketServerCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.security.rsocket.core.SecuritySocketAcceptorInterceptor;

@Bean
RSocketServerCustomizer springSecurityRSocketSecurity(
        SecuritySocketAcceptorInterceptor interceptor) {

    return server -> server.interceptors(registry ->
            registry.forSocketAcceptor(interceptor));
}
```

If you forget to attach the interceptor to a manually built server, the authorization configuration bean may exist while actual requests bypass that security layer. When testing, verify both the DSL configuration and the RSocket server initialization path.

## 10. Testing Authentication and Authorization

Tests should cover both success and failure cases. You can use integration tests with `RSocketRequester`, test tokens issued by a test issuer or a mocked `ReactiveJwtDecoder`, and Reactor Test's `StepVerifier`.

| Scenario | Token / Authority | Route | Expected Result |
|---|---|---|---|
| Missing token | No token | `orders.create` | Authentication rejected |
| Invalid signature or expired token | Invalid JWT | `orders.create` | Authentication rejected |
| Missing scope | Valid token, lacks `SCOPE_orders.write` | `orders.create` | Authorization rejected |
| Matching scope | Valid token, has `SCOPE_orders.write` | `orders.create` | Request forwarded to handler |
| Missing admin role | Lacks `ROLE_ADMIN` | `admin.users` | Authorization rejected |
| Has admin role | Has `ROLE_ADMIN` | `admin.users` | Request forwarded to handler |
| No specific route rule | Valid token | Other routes | Allowed if satisfying `anyRequest().authenticated()` |

Example testing a rejected request with `StepVerifier`:

```java
StepVerifier.create(
        requester.route("orders.create")
                .metadata(readOnlyToken, BEARER_AUTHENTICATION)
                .data(command)
                .retrieveMono(OrderReceipt.class))
    .expectError()
    .verify();
```

The test snippet assumes `requester`, `readOnlyToken`, and `command` have been prepared in the test. In real tests, assert the specific exception type or error signal matching your RSocket Java version and how the server propagates errors. Do not assume every RSocket error is HTTP 401 or 403; RSocket does not return HTTP statuses for requests like an HTTP endpoint.

Distinguish two error types:

- **Authentication failure**: missing token, invalid signature, expired, or unacceptable token.
- **Access denied**: token was authenticated, but the principal lacks the required authority.

Also test requests without a route, mismatched route patterns, missing authentication metadata, rejected SETUP, and requests sharing a connection across different principals.

## 11. Common Errors and Remediation

| Error | Cause | Remediation |
|---|---|---|
| `RSocketSecurity` configured, yet requests are not blocked | Security interceptor not attached to a manually built server | Check `SecuritySocketAcceptorInterceptor` and `RSocketServerCustomizer` |
| Token present in metadata, yet server does not authenticate | Wrong Bearer extension MIME type or `.jwt()` not enabled | Use `message/x.rsocket.authentication.bearer.v0` and `.jwt(Customizer.withDefaults())` |
| Requests sharing a connection receive the wrong identity | Authenticated only at SETUP while multiple users share the connection | Send the token on each request |
| Connection fails right at SETUP | `setup().authenticated()` rule while client sends no credentials in SETUP | Permit SETUP if using request-time auth or send credentials in SETUP |
| User with scope is still rejected | Authority in rule does not match authority derived from JWT claims | Check `scope`/`scp` and the `SCOPE_` prefix |
| Admin route disallowed | `hasRole("ADMIN")` checks `ROLE_ADMIN` | Grant the proper role or use `hasAuthority` with the actual authority |
| Route rule has no effect | `anyRequest()` declared before specific routes | Move specific routes before general rules |
| Valid token accepted by a different service | Audience not validated | Configure an audience validator for the resource server |
| Tenant metadata spoofed | Trusting client-supplied tenant value directly | Cross-check tenant against the authenticated principal and authorized data |

Operational notes:

1. Use HTTPS/TLS appropriate for the RSocket transport to protect tokens and payloads in transit.
2. Do not treat route or tenant metadata as authentication proof. Clients can fabricate metadata.
3. Do not log access tokens, usernames/passwords, or sensitive metadata.
4. Set reasonable token lifetimes and handle token refresh on the client side.
5. Validate issuer, signature, expiration, audience, and required claims before using a JWT for authorization.
6. If you want undeclared routes denied by default, use `anyRequest().denyAll()` after permitted rules instead of `anyRequest().authenticated()`.
7. When changing the route matcher or separator, retest all patterns in use. RSocket routes commonly use dots as separators, such as `orders.read.one`, instead of URL paths with slashes.
8. If using both route authorization and method security, review policies at both layers so no critical service method is left uncovered.

## 12. Implementation Checklist

- [ ] Clearly chose SETUP authentication, per-request authentication, or a combination of both.
- [ ] Connections shared among multiple users authenticate each request individually.
- [ ] Server has `@EnableRSocketSecurity` enabled.
- [ ] `PayloadSocketAcceptorInterceptor` is built and attached to the RSocket server.
- [ ] JWT uses the Bearer Token Authentication Metadata Extension with the correct MIME type.
- [ ] `ReactiveJwtDecoder` verifies issuer, signature, expiration, and audience per policy.
- [ ] Specific route rules are declared before `anyRequest()` and `anyExchange()`.
- [ ] `hasRole` and `hasAuthority` match actual authorities.
- [ ] Requests without dedicated rules still go through the chosen fallback policy.
- [ ] Client-supplied metadata is never used as standalone authorization proof.
- [ ] Transport is protected with TLS when transmitting tokens or credentials.
- [ ] Integration tests cover missing tokens, invalid tokens, insufficient permissions, and valid permissions.
- [ ] Method security is enabled if business logic must be protected at the service layer.

## References

- [Spring Security Reference — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [Spring Security 6.3 API — RSocketSecurity](https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html)
- [Spring Security 6.3 API — SimpleAuthenticationEncoder](https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/rsocket/metadata/SimpleAuthenticationEncoder.html)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot 3.3 API — RSocketServerCustomizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/rsocket/server/RSocketServerCustomizer.html)
