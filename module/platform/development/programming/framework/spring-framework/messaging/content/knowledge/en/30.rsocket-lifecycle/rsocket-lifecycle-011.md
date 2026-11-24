# TLS, Connection Identity, and Per-Request Authorization

> Scope: securing RSocket connections with TLS, authenticating identity at connection setup or per request, and authorizing by route, principal, and business data in Spring Security.

## 1. Objectives

After this lesson, you will be able to:

- Distinguish TLS, authentication, and authorization.
- Choose the right authentication timing: at `SETUP`, on each request, or both combined.
- Configure TLS for RSocket TCP and RSocket over WebSocket in Spring Boot.
- Understand the roles of server certificates, trust stores, and mutual TLS (mTLS).
- Configure Spring Security RSocket with `@EnableRSocketSecurity`, `RSocketSecurity`, and `PayloadSocketAcceptorInterceptor`.
- Write authorization rules by setup, route, role, and request context.
- Properly handle scenarios where one connection is shared by multiple users.

## 2. Three Protection Layers to Distinguish

A secure RSocket system typically needs three collaborating layers:

| Layer | Question Answered | Typical Mechanism |
| --- | --- | --- |
| Transport security | Can data be eavesdropped or altered on the network? Is the server truly the server we intend to reach? | TLS, X.509 certificates, hostname verification |
| Authentication | Who is connecting or sending the request? | JWT, bearer token, username/password metadata, client certificate mapped to a principal |
| Authorization | Which actions is that identity allowed to perform on which resources? | Roles, authorities, route rules, tenant or data-ownership checks |

TLS protects the transport channel. It does not by itself decide whether a user can read an account or delete an order. Likewise, a valid JWT proves identity and token claims per the verification policy; the application must still decide resource access rights.

RSocket is an application protocol running over a transport such as TCP or WebSocket. Thus, TLS is configured on the transport. RSocket authentication metadata is handled at the protocol/application layer. Without TLS, tokens or sensitive data inside payload metadata can be observed on the wire.

## 3. TLS for RSocket

### 3.1. What Does TLS Protect?

TLS creates an encrypted channel between both ends of the transport. In a standard TLS setup:

1. The client verifies the server certificate signed by a CA it trusts.
2. The client verifies the server's hostname matches the identity in the certificate.
3. Both sides negotiate cipher suites and session keys.
4. Data transmitted over the channel is protected for confidentiality and integrity.

One-way TLS typically authenticates the server. With mutual TLS (mTLS), the server also requires the client to present a certificate; the server verifies that certificate using a trust store. mTLS suits service-to-service communication or environments requiring workload identity at the transport layer.

A TLS certificate represents an endpoint or workload. It does not inherently represent the end user using that endpoint. If a gateway uses one certificate to open an RSocket connection and forwards requests for many users, the certificate identifies only the gateway. To authorize per user, add identity on each request or use a verified and trusted identity propagation mechanism.

### 3.2. Configuring TLS for Standalone RSocket TCP with Spring Boot

For a standalone RSocket server, Spring Boot supports `spring.rsocket.server.ssl.*` properties. Example using a PKCS12 keystore for the server certificate and a trust store containing the CA that signs client certificates:

```yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 9898
      ssl:
        enabled: true
        key-store: classpath:rsocket-server.p12
        key-store-type: PKCS12
        key-store-password: ${RSOCKET_KEYSTORE_PASSWORD}
        trust-store: classpath:rsocket-client-ca.p12
        trust-store-type: PKCS12
        trust-store-password: ${RSOCKET_TRUSTSTORE_PASSWORD}
        client-auth: need
```

`client-auth: need` requires the client to send a certificate and the server verifies it against the trust store. This configuration enables mTLS. If only one-way TLS is needed, omit the trust store and set `client-auth: none` or use your Boot version's appropriate default.

Never place keystore passwords directly in committed configuration files. Use environment variables, a secret manager, or your deployment platform's secret management. Protect private keys and restrict read permissions on certificate files.

The properties above belong to Spring Boot and the standalone RSocket server. If RSocket is attached to a WebFlux Web Server via a WebSocket mapping path, the endpoint shares the web server's TLS connector; configure certificates via the web server's `server.ssl.*`. Clients connect using a `wss://...` URL. Do not mistakenly configure standalone RSocket server SSL for a WebSocket endpoint sharing the HTTPS port.

### 3.3. Configuring TLS on the TCP Client

When a custom trust store or mTLS is needed on the client, you can create a `ClientTransport` from a TLS-enabled Reactor Netty `TcpClient`, then pass that transport to `RSocketRequester.Builder`:

```java
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import io.rsocket.transport.ClientTransport;
import io.rsocket.transport.netty.client.TcpClientTransport;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.netty.tcp.TcpClient;

import java.io.File;

SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(new File("certs/server-ca.pem"))
        .build();

TcpClient tcpClient = TcpClient.create()
        .host("rsocket.example.com")
        .port(9898)
        .secure(ssl -> ssl.sslContext(sslContext));

ClientTransport transport = TcpClientTransport.create(tcpClient);

RSocketRequester requester = RSocketRequester.builder()
        .transport(transport);
```

This is a client-side transport example; the application still needs metadata, codecs, and connection lifecycle handling per its contract. `trustManager` provides the CA the client trusts. For mTLS, add the client certificate and private key to the SSL context:

```java
SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(new File("certs/server-ca.pem"))
        .keyManager(
                new File("certs/client.crt"),
                new File("certs/client.key"))
        .build();
```

The server side must enable client authentication and trust the CA that signed `client.crt`. Never disable certificate or hostname verification to work around connection errors in production. Fix the certificate chain, trust store, hostname, or TLS configuration properly.

### 3.4. TLS over WebSocket

If RSocket runs over WebSocket, use `wss://` to protect WebSocket with TLS. When Spring Boot integrates RSocket into a WebFlux Web Server, configure TLS on the web server, for example:

```yaml
server:
  ssl:
    enabled: true
    key-store: classpath:web-server.p12
    key-store-type: PKCS12
    key-store-password: ${WEB_KEYSTORE_PASSWORD}

spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
```

Clients use the corresponding endpoint, such as `wss://api.example.com/rsocket`. If TLS is terminated at a load balancer or ingress, clearly identify which hops are encrypted. If a proxy forwards to the service over an internal network, protect the internal hop with TLS or a properly controlled and verified network boundary.

## 4. Identity at Connection Setup

### 4.1. SETUP and Connection-Level Identity

When opening an RSocket connection, the client sends a `SETUP` frame. This frame can contain initial data and metadata. `RSocketRequester.Builder` provides these methods:

- `setupData(Object)`: data for the `SETUP` frame.
- `setupMetadata(Object, MimeType)`: metadata for the `SETUP` frame.
- `setupRoute(String, Object...)`: route attached to `SETUP` if used by the application.

The responder can handle the connection start event with `@ConnectMapping`. Spring Security can also authenticate metadata in `SETUP` and apply dedicated rules via `authorizePayload(...).setup()`.

Authenticating at `SETUP` fits when one connection represents exactly one principal for the connection's entire lifecycle, such as a mobile app opening a dedicated connection for the signed-in user. Once the connection is authenticated, requests on the connection can use the identity attached to the connection per the security configuration.

What needs management is the connection lifecycle. When a user signs out, a token expires, permissions are revoked, or the user switches accounts, the application must close or re-authenticate the connection per policy. A long-lived connection should not retain an old identity indefinitely.

### 4.2. When Is Connection-Level Identity Insufficient?

Suppose a backend gateway opens one shared RSocket connection to a target service. Hundreds of end users send requests through that gateway. At the transport and `SETUP` layer, the target service sees only one gateway connection.

If authentication occurs only at `SETUP`, every request on that same connection can be seen under the gateway's identity. The target service cannot distinguish user A from user B to check per-user data ownership.

In this situation, authenticate on each request using a dedicated token or identity metadata. Never take a user id from the data payload or route and trust that value directly; the requester can alter values itself. Identity must come from credentials verified by the server.

## 5. Authenticating on Each Request

### 5.1. Request Metadata

Metadata on the initial request frame contains routing information and can contain credentials. With composite metadata, one request can carry multiple entries with separate MIME types, such as route and bearer authentication metadata.

Spring Security supports Simple Authentication Metadata Extension and Bearer Token Authentication Metadata Extension. For new applications, bearer tokens/JWTs are usually a better fit when an OAuth 2.0 or OpenID Connect issuer is already in place.

### 5.2. Sending a Bearer Token on Every Request

Example client attaching a JWT to metadata for each request:

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
        "message/x.rsocket.authentication.v0");

BearerTokenMetadata userToken = new BearerTokenMetadata(jwtForCurrentUser);

Mono<AccountView> result = requester
        .route("account.read.{accountId}", accountId)
        .metadata(userToken, authenticationMimeType)
        .retrieveMono(AccountView.class);
```

The example focuses on the request metadata portion. `jwtForCurrentUser` must be a valid token issued by the authentication system. The server side needs a configured JWT decoder and matching authorization rules. Never log tokens in logs, exception messages, or metric labels.

If using username/password metadata, Spring Security provides `simpleAuthentication()`, and the client can register `SimpleAuthenticationEncoder` in `RSocketStrategies`. Simple Authentication suits certain internal systems; legacy Basic Authentication metadata remains only for backward compatibility. Do not invent a custom password format inside metadata.

## 6. Spring Security RSocket

### 6.1. Core Components

| Component | Role |
| --- | --- |
| `@EnableRSocketSecurity` | Enables RSocket security infrastructure in Spring Security |
| `RSocketSecurity` | DSL for configuring payload authentication and authorization |
| `AuthenticationPayloadInterceptor` | Converts credentials in payloads into `Authentication` via `ReactiveAuthenticationManager` |
| `AuthorizationPayloadInterceptor` | Enforces permissions on `PayloadExchange` via `ReactiveAuthorizationManager` |
| `PayloadSocketAcceptorInterceptor` | Combines payload interceptors for RSocket |
| `SecuritySocketAcceptorInterceptor` | Connects payload security interceptors to the RSocket server acceptor |
| `ReactiveJwtDecoder` | Verifies and decodes JWTs |

With Spring Boot and the right RSocket/Spring Security dependencies, Boot automatically registers `SecuritySocketAcceptorInterceptor` via auto-configuration. Without Boot auto-configuration, attach the interceptor to the server manually.

### 6.2. Configuring JWT and Payload-Based Authorization

The following example illustrates a service requiring the `rsocket.connect` scope to open a connection, authenticating JWTs on requests, checking authorities by route, and denying unmatched exchanges:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@EnableRSocketSecurity
class RSocketSecurityConfiguration {

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        return ReactiveJwtDecoders.fromIssuerLocation(
                "https://identity.example.com");
    }

    @Bean
    PayloadSocketAcceptorInterceptor rsocketSecurity(
            RSocketSecurity rsocket) {
        rsocket
            .authorizePayload(authz -> authz
                .setup().hasAuthority("SCOPE_rsocket.connect")
                .route("account.read.{accountId}")
                    .access((authentication, context) ->
                        checkAccountAccess(authentication, context))
                .route("admin.user.delete")
                    .hasAuthority("SCOPE_admin")
                .anyRequest().authenticated()
                .anyExchange().denyAll()
            )
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }
}
```

This is an illustrative configuration; `checkAccountAccess(authentication, context)` is an application business check that must be implemented with real data access permissions. The JWT decoder fetches issuer metadata from the configured URL, and verifies signatures and token conditions per Spring Security configuration.

The example uses `hasAuthority("SCOPE_...")` because Spring Security's default JWT authentication maps scopes to authorities prefixed with `SCOPE_`. If the token uses a `roles` claim or custom authority names, configure a matching converter; only then use `hasRole(...)` if authorities are mapped using the `ROLE_...` convention.

The `setup().hasAuthority("SCOPE_rsocket.connect")` rule guards opening connections. In a combined model, the client sends a service token with scope `rsocket.connect` at `SETUP`, then sends the user's JWT on each request. The service token does not replace the user token.

If the application does not need identity authentication at `SETUP`, you can permit setup per system policy and require authentication on requests. Do not keep a setup rule requiring a scope if clients do not send credentials with that scope, as the connection will be rejected immediately upon establishment.

### 6.3. Sending Tokens at SETUP and on Each Request

In a gateway model sharing a connection, the client can send the workload token at setup and the user token on requests:

```java
MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
        "message/x.rsocket.authentication.v0");

BearerTokenMetadata serviceToken =
        new BearerTokenMetadata(jwtForGateway);

RSocketRequester requester = RSocketRequester.builder()
        .setupMetadata(serviceToken, authenticationMimeType)
        .transport(secureTransport);

BearerTokenMetadata userToken =
        new BearerTokenMetadata(jwtForCurrentUser);

Mono<AccountView> account = requester
        .route("account.read.{accountId}", accountId)
        .metadata(userToken, authenticationMimeType)
        .retrieveMono(AccountView.class);
```

The token in `SETUP` should grant only the permissions needed to establish the connection. The token on the request identifies the user executing the specific operation. The service checks both connection permission and user permission for the route/resource.

For a dedicated single-user connection, you can authenticate at `SETUP` and apply `.anyRequest().authenticated()` to requests. For a shared connection, authenticate every request or propagate user identity via an equivalently verified mechanism.

### 6.4. Simple Authentication

If using username/password metadata, server configuration can use:

```java
rsocket
    .authorizePayload(authz -> authz
        .anyRequest().authenticated()
        .anyExchange().denyAll()
    )
    .simpleAuthentication(Customizer.withDefaults());
```

The client must register the matching encoder:

```java
RSocketStrategies strategies = RSocketStrategies.builder()
        .encoder(new SimpleAuthenticationEncoder())
        .build();
```

When sending credentials in `SETUP`, use `setupMetadata(credentials, authenticationMimeType)`. When sending on requests, use `.metadata(credentials, authenticationMimeType)`. Credentials must be protected with TLS and verified via `ReactiveAuthenticationManager`/user store. Never use default passwords or hard-coded passwords in production.

## 7. Per-Request Authorization

### 7.1. Authorizing by Route

`authorizePayload` lets you write rules based on `PayloadExchange`. Common cases include:

- `.setup()`: applies to the connection setup frame.
- `.route("...")`: applies to a specific route or route pattern.
- `.anyRequest()`: applies to requests that have request-initiating metadata.
- `.anyExchange()`: applies to remaining exchanges, including payloads without corresponding metadata.

Rules are evaluated in declaration order. The first matching rule applies. Therefore, place specific routes before general rules and end with an explicit default policy, typically requiring authenticated or deny.

Example:

```java
.authorizePayload(authz -> authz
    .setup().hasAuthority("SCOPE_rsocket.connect")
    .route("profile.me").authenticated()
    .route("admin.user.delete").hasAuthority("SCOPE_admin")
    .anyRequest().authenticated()
    .anyExchange().denyAll()
)
```

In this example, `profile.me` requires an authenticated identity; deleting a user requires the `SCOPE_admin` authority; other requests must be authenticated; unmatched exchanges without metadata are denied. Design rules around your real API and avoid letting a broad rule grant access ahead of sensitive rules.

### 7.2. Authorization by Resource, Tenant, and Owner

Roles usually describe only coarse-grained permissions. For instance, role `USER` may allow reading certain resources, yet does not mean a user may read every account.

For route `account.read.{accountId}`, the application needs to verify:

1. The JWT has a valid signature, is unexpired, and matches issuer/audience policies.
2. The principal has the authority to read accounts.
3. `accountId` exists and belongs to a tenant or user the principal is permitted to access.
4. Access remains valid under current business state.

Spring Security lets you use `.access((authentication, context) -> ...)` for custom checks. Route variables such as `accountId` can be read from the authorization context. Never trust an account id sent by the client merely because the route matched.

Ownership checks belong in the service/domain layer or a custom authorization manager where real permissions can be queried. Checking only `hasRole("USER")` can let users sharing the same role accidentally read each other's resources.

### 7.3. AuthenticationPrincipal in Handlers

Handlers may need the principal for auditing or passing context into services. Spring Security provides `AuthenticationPrincipalArgumentResolver`; if your messaging handler configuration does not register this resolver automatically, add it to `RSocketMessageHandler` via `ArgumentResolverConfigurer`.

Another option in reactive code is reading the security context via `ReactiveSecurityContextHolder` inside the reactive chain. Never store a request's principal in a shared mutable field on a singleton controller, as multiple requests can run concurrently over the same connection.

## 8. Connection Identity vs. Per-Request Identity: Choosing a Model

| Scenario | Authenticate at SETUP | Authenticate on Request | Rationale |
| --- | --- | --- | --- |
| Single user, dedicated connection | Appropriate | May be unnecessary if identity is safely bound to the connection | Principal is stable for the connection lifecycle |
| Gateway sharing one connection across many users | Use for gateway/workload identity if needed | Required to distinguish users | One connection does not represent a single end user |
| Service-to-service with mTLS | TLS/mTLS verifies workload | Can add JWT when per-operation permissions are needed | Certificate identifies workload; token can carry application permissions |
| WebSocket connection from browser | Can authenticate at setup | Often uses per-request tokens when multiple users go through a gateway | Cookie/HTTP handshake and request identity must be designed consistently |

A combined model is often useful: mTLS or a service token restricts which workloads can open a connection; per-request JWTs identify the user and permissions for each operation. Each layer needs its own policy and must never implicitly inherit permissions from another layer.

## 9. Common Errors

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| TLS handshake fails | Server certificate untrusted, missing intermediate certificate, or incompatible protocol/cipher | Check certificate chain, trust store, and TLS protocols on both sides |
| Hostname verification fails | Connection host does not match SAN in certificate | Use DNS name matching certificate or reissue certificate with proper SAN |
| mTLS rejected | Client sends no certificate or server does not trust signing CA | Check `client-auth`, trust store, and client key pair |
| Connection succeeds but requests are rejected | Missing credentials, wrong issuer/audience, expired token, or missing authority | Check JWT decoder, claim mapping, and matching rule |
| All users through gateway share the same permissions | Only gateway identity authenticated at SETUP | Send verified user credentials on each request |
| User A can read User B's data | Only role checked, missing owner/tenant check | Add object-level authorization checks |
| Sensitive route permitted by broad rule | Broad rule precedes specific rule or fallback is too permissive | Reorder rules; use default deny where appropriate |
| Token exposed in logs | Logging full metadata or exception payloads | Redact credentials and restrict logged data |
| Stale permissions remain valid on long-lived connection | Authenticated only at setup without handling token expiry/revocation | Enforce connection lifetime, reconnect, or re-authenticate per request |

Transport-level TLS check command:

```bash
openssl s_client -connect rsocket.example.com:9898 \
  -servername rsocket.example.com -showcerts
```

This command helps inspect the TLS handshake, certificate chain, and hostname at the OpenSSL level. It does not prove that RSocket `SETUP`, MIME types, authentication metadata, or authorization rules work properly. After TLS passes, run actual RSocket tests.

## 10. Security Testing

An integration test suite should cover these cases:

1. TLS connection with a valid certificate succeeds.
2. Untrusted certificate or mismatched hostname is rejected.
3. With mTLS, a client without a certificate is rejected when the server requires `client-auth: need`.
4. `SETUP` credentials lacking connection authority are rejected.
5. Expired, wrong-issuer, or invalid-signature JWTs fail authentication.
6. Requests missing a token are rejected on routes requiring authenticated.
7. Regular users cannot call admin routes.
8. Two users with the same role cannot access resources belonging to another tenant/user.
9. Requests matching no rule are handled per the chosen fallback policy.
10. Shared connections send distinct tokens per request and the server distinguishes principals properly.
11. Tokens never appear in application logs, trace attributes, or metric labels.

Also test reconnect and token expiration on long-lived connections. A single test showing the first request succeeds is not enough to prove identity policies remain sound over long-lived connections.

## 11. Implementation Checklist

- [ ] TLS is enabled on the RSocket transport or corresponding WebSocket endpoint.
- [ ] Client verifies the server's certificate chain and hostname.
- [ ] Private keys and keystore passwords are stored in a secret manager or secure environment.
- [ ] If using mTLS, server requires client certificates and trusts the proper CA.
- [ ] Application clearly separates workload identity from end-user identity.
- [ ] Decided whether to authenticate at SETUP, per request, or both.
- [ ] Spring Security RSocket interceptor is attached to the server.
- [ ] JWT decoder verifies issuer, signature, expiration, and audience per system requirements.
- [ ] Specific route rules precede general rules.
- [ ] Explicit fallback policy exists for unmatched requests.
- [ ] Tenant/owner permission checks are enforced for specific resources.
- [ ] Expiration, credential revocation, and reconnect policies exist for long-lived connections.
- [ ] Logs and traces strip tokens, passwords, and sensitive metadata.
- [ ] Integration tests cover TLS, authentication, authorization, and connection sharing.

## 12. References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): transport, SETUP, requester, metadata, and annotated responders.
- [Spring Security Reference — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html): setup-vs-request authentication, Simple Authentication, JWT, and authorizePayload.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): RSocket server auto-configuration and transport.
- [Spring Boot Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.rsocket.server.ssl.*` and `server.ssl.*`.
- [Reactor Netty Reference — TCP Server](https://projectreactor.io/docs/netty/release/reference/tcp-server.html): TLS context for TCP server.
- [Reactor Netty Reference — TCP Client](https://projectreactor.io/docs/netty/release/reference/tcp-client.html): TLS context for TCP client.
- [RSocket Protocol](https://github.com/rsocket/rsocket/blob/master/Protocol.md): SETUP, request frames, transport, and payload.

Boot configuration examples use current Spring Boot properties; exact APIs may vary across Spring Framework, Spring Security, Spring Boot, and RSocket Java branches. Always verify against your project's actual dependency versions before copying configuration.
