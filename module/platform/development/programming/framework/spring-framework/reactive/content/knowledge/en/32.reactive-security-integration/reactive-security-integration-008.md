# Distinguishing WebFlux Security from In-Depth OAuth2 System Design

## 1. What Needs to Be Distinguished

Spring WebFlux is a reactive HTTP stack. Spring Security for WebFlux protects HTTP requests and Publishers executing within an application. OAuth 2.0 is an authorization delegation framework across multiple systems; OpenID Connect (OIDC) adds an identity authentication layer on top of OAuth 2.0.

Four distinct scopes:

- **WebFlux security:** is the request allowed into the endpoint, who is authenticated, which authorities are required, and how does the security context propagate across `Mono`/`Flux`?
- **OAuth2 Resource Server:** the API receives and validates bearer access tokens issued elsewhere, then enforces scopes, roles, and business authorization.
- **OAuth2 Client/OIDC Login:** the application redirects users to an Identity Provider to log in, or obtains valid access tokens before calling other APIs.
- **Authorization platform design:** operating an authorization server, client registration, grants/PKCE, consent, token issuance, refresh, JWKS, revocation, introspection, tenant isolation, auditing, and high availability.

**First conclusion:** adding Spring Security and a `SecurityWebFilterChain` protects a WebFlux API, **not automatically creating an OAuth2 Authorization Server**. Conversely, building a solid authorization server does not replace resource-level permission checks inside the API.

## 2. OAuth2 Roles and System Boundaries

| OAuth2 Role | Responsibility | Example |
| --- | --- | --- |
| Resource Owner | Entity owning/controlling access to a resource | User who owns an order |
| Client | Application requesting access | SPA, BFF, backend service, mobile app |
| Authorization Server | Authenticates/authorizes and issues access tokens | Organization's Identity Provider |
| Resource Server | API holding protected data and validating tokens | Orders API built on Spring WebFlux |

General flow:

~~~text
  User / Browser
        |
        v
  Client (SPA/BFF)
        | \
        |  \--- Authorization Code + PKCE ---> Authorization Server
        |                                      - Login/MFA
        |                                      - Consent/client policy
        |                                      - Issue/refresh/revoke tokens
        |                                      - JWKS/introspection
        |<---------------- access token ---------|
        |
        | Authorization: Bearer <access-token>
        v
  Gateway (optional)
        |
        v
  Spring WebFlux Resource Server
    1. Authenticate bearer token
    2. Validate signature/issuer/audience/time
    3. Map scopes to authorities
    4. Authorize route + owner/tenant/resource
        |
        v
    Database / Downstream API
~~~

A product may have one authorization server and dozens of WebFlux resource servers. Not every microservice needs to issue tokens itself. Likewise, a `WebClient` making HTTP calls does not automatically become an authorized OAuth2 client: it must use an access token issued for the right resource/audience.

## 3. `SecurityWebFilterChain` Is the Request Protection Layer

In reactive Spring Security, the core components include:

- `@EnableWebFluxSecurity`: enables reactive security configuration when needed.
- `SecurityWebFilterChain`: combines `WebFilter`s and request matching/policy rules.
- `ServerHttpSecurity`: DSL for configuring authorization, resource server, login, CORS/CSRF, and other mechanisms.
- `ReactiveAuthenticationManager`: reactive authentication by provider.
- `ReactiveAuthorizationManager`: permit/deny decision logic.
- `ReactiveSecurityContextHolder`: accesses the security context via Reactor Context.
- `@EnableReactiveMethodSecurity` and `@PreAuthorize`: enforces method-level authorization on reactive methods.

Example protecting an API by scope:

~~~java
@Configuration
@EnableWebFluxSecurity
class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .csrf(csrf -> csrf.disable())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/public")
                        .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:write")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

This snippet is for a **stateless bearer-only API**. A JWT decoder must be configured with the appropriate issuer/JWKS. `csrf.disable()` is valid only when the application does not rely on browser auto-sent cookies/sessions to authenticate state-changing requests. For OIDC login using session cookies or a BFF, do not copy this configuration mechanically.

### 3.1. Authentication and Authorization Differ

- **Authentication:** confirms the caller's identity/credentials. For example, a valid Bearer token identifies the subject.
- **Authorization:** decides whether the caller may read/write a resource. For example, a user holding scope `orders:read` who does not own order 42 must still be denied.

Spring Security handles both well in the request pipeline; however, an OAuth2 system also defines **who issues tokens and under what conditions**.

### 3.2. Reactor Context, Not Relying on `ThreadLocal`

A reactive chain can switch threads. Security context is integrated via the Reactor Context:

~~~java
Mono<String> currentUser =
        ReactiveSecurityContextHolder.getContext()
                .map(context ->
                        context.getAuthentication().getName());
~~~

This must be subscribed within an authenticated reactive context. Do not assume `ThreadLocal`-based `SecurityContextHolder.getContext()` stays accurate inside `flatMap` or `publishOn`.

### 3.3. Method Security

~~~java
@Configuration
@EnableReactiveMethodSecurity
class MethodSecurityConfiguration {
}

@Service
class DocumentService {

    @PreAuthorize("hasAuthority('SCOPE_documents:read')")
    Mono<Document> read(String id) {
        return repository.findById(id);
    }
}
~~~

This is an illustrative snippet requiring project-defined `Document` and `repository`. `@PreAuthorize` enforces coarse-grained permissions, while the service must still check per-document ownership/tenant/ACL.

## 4. OAuth2 Is Not Equivalent to OIDC Login

| Concept | Question Answered | Primary Subject |
| --- | --- | --- |
| Authentication | Who is calling? | User/service |
| Authorization | Is access to this resource permitted? | Subject + resource |
| OAuth 2.0 | How does a client receive delegated permission to access a resource? | Client, authorization/resource server |
| OIDC | How does a client verify a user's login event/identity? | OIDC client / Identity Provider |
| Spring Security WebFlux | How are security rules enforced in the reactive request chain? | WebFlux app |

OAuth2 is a delegation framework, not a complete identity login protocol. OIDC supplies ID tokens, UserInfo, and standard identity verification mechanisms. OAuth2 Login with certain providers can integrate login via provider-specific APIs, but should not be conflated with standard OIDC.

### 4.1. Access Token, ID Token, Refresh Token

| Token | Used For | Should Not Be Used To |
| --- | --- | --- |
| Access token | Resource server protecting APIs | Act as an ID token for clients |
| ID token | OIDC relying party/client verifying login details | Act as a Bearer access token for APIs |
| Refresh token | OAuth2 client obtaining new access tokens | Call resource servers |

**Never send an ID token to an API in place of an access token.** An ID token's audience is the logging-in client, not necessarily the API. Never send refresh tokens to resource servers. For public clients, refresh tokens must be protected under stricter policies since devices/browsers cannot safely hold long-lived secrets.

## 5. Three Roles WebFlux Commonly Implements

### 5.1. Resource Server: Protecting APIs

Request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJ...
~~~

The resource server validates the bearer token and enforces route/resource policies. In Spring WebFlux:

- JWT: `ReactiveJwtDecoder` validates signatures and claims.
- Opaque token: `ReactiveOpaqueTokenIntrospector` queries the authorization server.
- `SecurityWebFilterChain` checks authorities/routes.
- Business services enforce resource-level access.

A resource server is not responsible for issuing refresh tokens or handling OAuth consent.

### 5.2. OAuth2 Client: Obtaining Tokens to Call Other APIs

Reactive Spring Security supports `ReactiveOAuth2AuthorizedClientManager` and a `WebClient` filter:

~~~java
@Bean
WebClient oauthWebClient(
        ReactiveOAuth2AuthorizedClientManager manager) {

    ServerOAuth2AuthorizedClientExchangeFilterFunction oauth =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                    manager);

    return WebClient.builder()
            .filter(oauth)
            .build();
}
~~~

This is an integration snippet requiring OAuth2 client registrations, authorized-client selection, and token provider configuration. It does not mean every outbound request automatically receives a token; ensure tokens are sent only to matching hosts/audiences.

### 5.3. OAuth2/OIDC Login: User Sign-In

~~~java
@Bean
SecurityWebFilterChain loginChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(e ->
                    e.anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
}
~~~

This snippet illustrates a login client application, not an authorization server. It requires OAuth2 client registration, provider metadata, redirect URIs, session handling, and browser-login security controls.

## 6. Authorization Server Belongs to a Separate Architecture

An Authorization Server may need to handle:

1. User authentication/federation, MFA, and session management.
2. Public/confidential client registration and client authentication.
3. Redirect URI validation and grant policies.
4. Authorization Code, PKCE, client credentials, refresh, and additional grants.
5. Scope, consent, and delegated permission management.
6. Issuing access tokens, and ID tokens when providing OIDC.
7. Managing signing keys, JWKS, and key rotation.
8. Providing introspection, revocation, and metadata/discovery endpoints.
9. Securely storing authorizations, consents, client data, and secrets.
10. Auditing, rate limiting, high availability, threat monitoring, and incident recovery.

In Spring Security **7**, Spring Authorization Server functionality was integrated into the Spring Security ecosystem. The official authorization server guidance currently uses the **Servlet stack** with `HttpSecurity`, `SecurityFilterChain`, and `OAuth2AuthorizationServerConfigurer`. Do not assume `@EnableWebFluxSecurity` or reactive `SecurityWebFilterChain` automatically builds an authorization server.

| Concern | WebFlux Resource Server | Authorization Server |
| --- | --- | --- |
| Accepts Bearer access tokens | Yes | Not its primary job |
| Verifies IdP-signed JWTs | Yes | Supplies keys/issuer |
| Introspects tokens | Consumer | Provides endpoint |
| Checks routes/scopes | Yes | Defines scope policies |
| Checks resource owner/tenant | API business logic | Defines trust model |
| Issues access/refresh/ID tokens | No | Yes |
| Authorization Code + PKCE | Client may participate | Verifies code/verifier and issues tokens |
| Client registration and consent | Consumes policies | Manages |
| Signing key rotation | Consumes JWKS | Manages private keys and JWKS |
| Revocation endpoint | May call | Provides |
| High availability / token store | API HA | OAuth2 platform HA |

The token issuer can be a managed IdP or a self-hosted platform. Never decide to build an authorization server merely because the API runs on WebFlux.

## 7. Authorization Code + PKCE for Users

General flow:

~~~text
Client / Browser                Authorization Server           Resource Server
      |                                |                             |
      | Create verifier/challenge      |                             |
      |--- /authorize ---------------->|                             |
      |    client_id, redirect_uri     |                             |
      |    scope, state, challenge     |                             |
      |<-- Login / Consent ------------|                             |
      |--- Authenticate / Approve ---->|                             |
      |<-- Redirect ?code&state -------|                             |
      |--- /token -------------------->|                             |
      |    code, code_verifier         |                             |
      |<-- Access token ---------------|                             |
      |--- Bearer access token ------------------------------------->|
      |<-- API response ---------------------------------------------|
~~~

Key requirements:

- `code_verifier` must be sufficiently random and bound to a single authorization request.
- `code_challenge` normally uses S256; the server verifies the verifier at the token endpoint.
- `state` binds the authorization response to the client's request.
- `nonce` is critical when an OIDC client validates ID tokens in the corresponding flow.
- `redirect_uri` must be registered and matched strictly; never allow open redirects.
- Authorization codes must be short-lived and single-use.
- Public clients cannot protect a client secret the way confidential backend clients can.
- Protect access tokens from exposure in browser storage, URLs, and logs.

Do not pick the implicit flow or Resource Owner Password Credentials grant as defaults for new applications. Follow OAuth2 Security BCP guidelines and provider policies.

## 8. Client Credentials for Machine-to-Machine

~~~text
  Service A                     Authorization Server                   Service B
      |                                  |                                  |
      |-- Client authentication -------->|                                  |
      |   grant_type=client_credentials  |                                  |
      |<-- Access token -----------------|                                  |
      |-- Authorization: Bearer token ------------------------------------->|
      |<-- Response -------------------------------------------------------|
~~~

Client Credentials normally represent the service/client's own identity rather than a specific user. Never fabricate `sub=user123` to pretend user delegation exists. If downstream needs user context, design token relay or token exchange with dedicated permissions/audiences.

Server-to-server clients may use client secrets, private-key JWTs, or mTLS depending on security requirements; credentials must live in a secret manager/keystore rather than source code and must never be logged.

## 9. JWT Resource Server: What Must Be Validated?

A JWT has three parts:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Example payload (not a real token for calling an API):

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1820000000,
  "nbf": 1819999000,
  "iat": 1819998900,
  "scope": "orders:read",
  "tenant_id": "tenant-a"
}
~~~

### 9.1. Mandatory Validation by Design

1. Signature matches a trusted public key.
2. Signing algorithm is in an allowlist; never trust `alg` merely because the token declares it.
3. `iss` matches the configured issuer.
4. `aud` includes this API/resource server.
5. `exp` has not expired, `nbf` is valid, and clock skew has an explicit policy.
6. Appropriate token type/profile if the API requires the access-token JWT profile.
7. Scopes and authorities satisfy the endpoint.
8. The user is authorized for the actual resource and tenant.

Never simply Base64-decode the payload and read claims without verifying. A token issued for API A does not automatically grant access to API B even from the same issuer.

### 9.2. Spring Boot JWT Configuration

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
          audiences:
            - orders-api
          jwk-set-uri: https://identity.example.test/oauth2/jwks
~~~

The addresses above are examples. In production, use a trusted issuer and real JWK Set. `issuer-uri` must match `iss`; `audiences` checks `aud`; `jwk-set-uri` specifies the source of public keys.

When only `issuer-uri` is specified, the framework discovers metadata/JWKS. Specifying `jwk-set-uri` alongside `issuer-uri` can avoid startup discovery dependencies while still requiring issuer validation. Verify exact behavior for your Spring Security version and network/HA model.

### 9.3. Mapping Scopes to Authorities

JWT:

~~~json
{
  "scope": "orders:read orders:write"
}
~~~

Spring Security typically maps this to:

~~~text
SCOPE_orders:read
SCOPE_orders:write
~~~

Hence:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
.hasAuthority("SCOPE_orders:read")
~~~

Scopes, roles, and ownership are three distinct layers. `ROLE_ADMIN`, `SCOPE_admin`, and `permission:orders:read` are not automatically interchangeable. When an IdP uses custom claims, a tested converter is required to prevent privilege escalation.

### 9.4. 401 and 403

| Status | Typical Meaning |
| --- | --- |
| `401 Unauthorized` | Missing/invalid/expired bearer token or unauthenticated |
| `403 Forbidden` | Authenticated but lacking required authority/business permission |

Do not return 403 for every malformed token case; likewise, do not return 200 with an error body instead of HTTP semantics without a clear reason.

## 10. Opaque Tokens and Introspection

Opaque tokens do not require the API to decode token internals. The resource server calls an introspection endpoint on the authorization server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: "\${INTROSPECTION_CLIENT_SECRET}"
~~~

Spring WebFlux uses `ReactiveOpaqueTokenIntrospector`. The introspection server returns `active`, `scope`, `sub`, expiry, and metadata. If the token is not active, the request is rejected.

### 10.1. JWT vs. Opaque Token

| Criterion | Offline JWT Verification | Opaque Introspection |
| --- | --- | --- |
| Verification | Local signature + claims/JWKS | Remote introspection |
| Latency | Usually low once keys are cached | Depends on network/IdP |
| Revocation | May lag until `exp` without extra checks | Can reflect revocation per policy |
| Payload visibility | JWT payload is typically decodable, not encrypted by default | Token is usually opaque to the API |
| Operations | Key caching, issuer/audience, rotation | Introspection timeouts, caching, rate limits |
| Availability | API can verify during brief IdP outages if keys are cached | Stronger network dependency |

JWTs can also be introspected if the IdP supports it. Distinguish **token format** from **validation strategy**.

### 10.2. Token Revocation

- Short-lived JWTs shrink exposure windows but do not provide instant revocation on their own.
- Refresh token rotation and reuse detection reduce credential replay risk.
- Opaque introspection can check active status at call time.
- Caching introspection results improves performance at the cost of slower revocation propagation.
- If user/token lockout within seconds is required, dedicated SLA and architecture are needed rather than a single Spring flag.

## 11. WebFlux as Both Resource Server and OAuth2 Client

Multi-microservice pattern:

~~~text
Browser --> API A [Resource Server]
                  |
                  +-- WebClient [OAuth2 Client] --> API B [Resource Server]
                  |
                  +-- Database
~~~

Questions to answer:

1. Does API B need a service identity or a delegated user identity?
2. Does API A's access token have the right audience for API B?
3. May the original token be relayed or is token exchange required?
4. Should scopes be narrowed?
5. Who stores refresh tokens and when are they refreshed?
6. Are tokens prevented from being sent to non-allowlisted hosts on redirects?
7. If a user is revoked, how long do downstream tokens remain valid?

**Never relay bearer tokens arbitrarily.** A token issued for audience A is not automatically valid at B. Separate scopes and audiences per trust boundary; when needed, use IdP-supported token exchange or delegation.

`ReactiveOAuth2AuthorizedClientManager` and `WebClient` filters handle the mechanics of acquiring/attaching tokens, not the architectural decision of which token goes to whom.

## 12. CORS, CSRF, Cookies, and WebSocket

### 12.1. CORS Is Not Authentication

CORS is a browser policy governing whether JavaScript on another origin can read responses. It does not block `curl` or backend services from calling an API. `OPTIONS` preflights may carry no cookies; CORS must run before security authentication for preflights.

When browsers use `credentials: "include"`, actual responses must include a specific allowed origin and `allow-credentials: true`; wildcard origins are invalid for credentialed requests.

### 12.2. CSRF Depends on the Authentication Model

Browsers can automatically attach session cookies to requests, which is a core driver of CSRF. A stateless bearer-only API requiring an explicit `Authorization` header has a different threat model.

Do not disable CSRF merely because "we use OAuth2": OIDC login with session cookies, BFFs, or browser forms can still require CSRF protection. CORS does not replace CSRF.

### 12.3. SPA / BFF / Native / Machine Clients

- **BFF:** backend holds tokens, browser holds `HttpOnly`/`Secure`/`SameSite` session cookies, with CSRF defense and session lifecycle management.
- **SPA:** public client using Authorization Code + PKCE, with strict XSS controls and careful token storage.
- **Native:** system browser/user agent, redirect handling/PKCE, no embedded confidential secrets.
- **Machine:** client credentials and strong client authentication per policy.

Client secrets embedded in SPA JavaScript or mobile bundles can be extracted. Never treat them as confidential clients.

### 12.4. WebSocket and SSE

WebSocket starts with an HTTP handshake, but post-upgrade messages do not traverse HTTP request security filters the way new HTTP requests do. Authenticate the handshake, validate `Origin`, and protect sensitive commands/messages individually as needed. Do not rely on CORS to protect WebSockets.

SSE is HTTP streaming; browser native `EventSource` has limitations around custom headers. Do not blindly copy `fetch` bearer header strategies without checking client transport capabilities.

## 13. Non-Blocking Does Not Automatically Make Security Secure

WebFlux avoids blocking the event loop, yet security architecture still requires:

- Non-blocking HTTP clients for introspection/remote policy calls.
- Timeouts, bounded retries, and fail-closed behavior.
- TLS trust/hostname validation, and mTLS when required.
- Proper Reactor Context usage without abusing `ThreadLocal`.
- Never invoking blocking JDBC/LDAP/SDKs on the event loop.
- Rate limits toward authorization/introspection/JWKS endpoints.
- Redacting tokens, cookies, and PII from logs.
- Validating resource/tenant authorization inside services.

Wrapping a blocking security SDK in `Mono` without an appropriate scheduler still blocks. Nor does a scheduler turn an invalid token into a valid one.

## 14. Runnable Java 17+ Program: WebFlux Resource Server

This example builds an API that **validates JWTs and enforces scopes**, without **issuing tokens**. Tests use Spring Security's `mockJwt()` to focus on offline authorization testing without needing a live IdP.

Requirements:

- JDK 17+.
- Maven 3.6.3+.
- Spring Boot **4.1.2**.
- Maven Central access for initial dependency download.

### 14.1. Directory Structure

~~~text
webflux-resource-server-demo/
  pom.xml
  src/main/java/example/security/SecurityBoundaryApplication.java
  src/main/java/example/security/ApiSecurityConfiguration.java
  src/main/java/example/security/OrdersController.java
  src/main/resources/application.yml
  src/test/java/example/security/OrdersSecurityTest.java
~~~

### 14.2. `pom.xml`

Spring Boot 4.1 uses explicitly named starters for OAuth2 resource server and WebFlux testing.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-resource-server-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The older name `spring-boot-starter-oauth2-resource-server` still appears in older projects, whereas Boot 4.1 deprecates it in favor of `spring-boot-starter-security-oauth2-resource-server`.

### 14.3. Application Class

**src/main/java/example/security/SecurityBoundaryApplication.java**

~~~java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SecurityBoundaryApplication.class, args);
    }
}
~~~

### 14.4. Security Configuration

**src/main/java/example/security/ApiSecurityConfiguration.java**

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .csrf(csrf -> csrf.disable())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/public")
                        .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:write")
                        .pathMatchers(HttpMethod.GET, "/api/me")
                        .authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Rules:

- `GET /api/public` allows anonymous access.
- `GET /api/orders/{id}` requires `SCOPE_orders:read`.
- `POST /api/orders/{id}` requires `SCOPE_orders:write`.
- `GET /api/me` requires authentication.
- All other routes are denied.
- JWTs are validated by the resource server.
- CSRF is disabled solely for this stateless bearer-only demo; do not copy verbatim if cookie login is added.

### 14.5. Controller

**src/main/java/example/security/OrdersController.java**

~~~java
package example.security;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class OrdersController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/orders/{id}")
    public Mono<String> readOrder(@PathVariable String id) {
        return Mono.just("order:" + id);
    }

    @PostMapping("/orders/{id}")
    public Mono<String> updateOrder(@PathVariable String id) {
        return Mono.just("updated:" + id);
    }

    @GetMapping("/me")
    public Mono<String> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just("user:" + jwt.getSubject());
    }
}
~~~

The demo endpoints do not access real data. In production applications, you must verify the user has rights to the specific order ID before returning data, in addition to scope checks.

### 14.6. Resource Server Settings

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/demo
          audiences:
            - orders-api
~~~

This issuer is **merely an illustrative address**, not a real Identity Provider. Spring Security uses it to locate keys/metadata when validating real JWTs. The tests below use `mockJwt` and therefore do not contact an IdP. To run end-to-end with real tokens, replace the issuer with a real IdP and ensure `aud`, keys, algorithms, and scopes align.

### 14.7. Offline Authorization Tests with `WebTestClient`

**src/test/java/example/security/OrdersSecurityTest.java**

~~~java
package example.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class OrdersSecurityTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicRouteWithoutToken() {
        client.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void protectedRouteRejectsMissingToken() {
        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readScopeAllowsRead() {
        client.mutateWith(mockJwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("order:42");
    }

    @Test
    void readScopeCannotWrite() {
        client.mutateWith(mockJwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .post()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void writeScopeAllowsWrite() {
        client.mutateWith(mockJwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:write")))
                .post()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("updated:42");
    }

    @Test
    void principalSubjectVisible() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt.subject("alice")))
                .get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user:alice");
    }
}
~~~

`mockJwt` injects a test authentication into `WebTestClient` to focus on authorization rules. It **does not issue genuinely signed JWTs** and does not verify cryptographic validation.

### 14.8. Running the Demo

In the directory containing `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

**Expected test summary output:**

~~~text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
~~~

Maven console output also contains timings, logs, and other lines, so do not assume stdout consists solely of that line.

Once the app runs on default port 8080:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/orders/42
~~~

The first command returns 200 and body `public`. The second lacks a bearer token and typically returns 401. The demo **has no `/oauth2/token` endpoint**; to test real JWTs, configure a real IdP and obtain an access token with the right audience and scopes.

## 15. What Does `mockJwt` Test vs. Leave Untested?

| Case | Covered by `mockJwt`? | Needs Other Tests? |
| --- | --- | --- |
| Public route for anonymous | Yes | Optional HTTP integration |
| Read/write scope rules, 401/403 | Yes | Optional full-stack integration |
| JWT principal/`sub` in controller | Yes | Claim mapping integration |
| RSA/ECDSA JWT signature | No | Real signed JWT + decoder |
| `iss` and `aud` validation | Not proven by itself | Negative token tests |
| `exp`/`nbf` and clock skew | Not proven by itself | Decoder tests |
| JWKS metadata/key rotation | No | Mock IdP/JWKS server |
| Opaque introspection active/revoked | No | Stubbed introspection |
| Authorization Code + PKCE | No | Browser/IdP end-to-end |
| Cookie/session/CSRF | No | Browser/security tests |
| Tenant ownership in database | No | Business policy tests |

A system can pass every `mockJwt` test and still accept the wrong audience due to decoder misconfiguration. Test **policy** and **token validation** separately.

## 16. Token Lifecycle and Secrets

### 16.1. Access Tokens

Access tokens are bearer credentials. Choose TTLs balancing risk, UX, and refresh capability. Never put tokens in URLs, query strings, browser logs, tracing spans, or error responses. Use HTTPS/TLS, redact the `Authorization` header, and verify destinations before forwarding tokens via `WebClient`.

### 16.2. Refresh Tokens

Refresh tokens generally live longer than access tokens and require:

- Issuing only to permitted client types.
- Storing in storage suited to the threat model.
- Rotation or sender-constraining where needed.
- Reuse detection, revocation, and logout/session policies.
- Auditing by client/user/device.
- Zero exposure in logs and telemetry.

A Resource Server normally does not hold users' refresh tokens. That responsibility belongs to the token client and authorization server layers.

### 16.3. Signing Keys and JWKS Rotation

The Authorization Server manages **private signing keys**, while resource servers need **public verification keys**:

1. Publish the new public key via JWKS.
2. Begin signing new tokens with the new key per the rotation plan.
3. Retain the old public key while older tokens remain valid.
4. Respect cache TTLs and propagation delays.
5. Retire the old key once safe; maintain a playbook for private key compromise.

Never copy an IdP's private key into APIs to "verify JWTs". Never distribute unnecessary shared secrets across dozens of services.

### 16.4. Token Exchange

When API A calls API B on behalf of a user, design audience, scope narrowing, actor/user claims, TTL, and auditing. Token exchange must be supported by the IdP/authorization server under policy. Never let APIs rewrite JWT claims and re-sign them without explicit trust delegation.

## 17. Multi-Tenancy and Resource-Level Authorization

A JWT containing a tenant claim or read scope does not automatically prove the user may read every resource.

Two layers of checks:

1. **Coarse-grained:** valid token, sufficient scopes/authorities to call the route.
2. **Fine-grained:** resource belongs to the tenant and owner/ACL permits access.

Illustrative example:

~~~java
Mono<Order> readOrder(String orderId, Jwt principal) {
    return orderRepository.findById(orderId)
            .filter(order -> order.tenantId()
                    .equals(principal.getClaimAsString("tenant_id")))
            .filter(order -> order.ownerId()
                    .equals(principal.getSubject()))
            .switchIfEmpty(Mono.error(
                    new AccessDeniedException("Not allowed")));
}
~~~

This snippet requires a real repository/`Order`. An owner-only policy may be too restrictive for managers; design delegated roles or tenant memberships separately. Prevent IDOR by verifying resource-to-subject relationships server-side, never trusting client-supplied tenant headers or IDs.

## 18. Decisions Required When Designing an In-Depth OAuth2 Platform

| Area | Mandatory Decisions |
| --- | --- |
| Identity | Local accounts, federation, SSO, MFA, account recovery |
| Clients | Public/confidential, registration, exact redirect URIs |
| Grants | Code+PKCE, client credentials, refresh, device, and additional grants |
| Token format | JWT/opaque, claims, scopes, audiences, TTL |
| Signing | Key algorithms, KMS/HSM, JWKS, rotation/recovery |
| Consent | Consent UX, retention, withdrawal, auditing |
| Sessions | Logout, session binding, step-up, re-authentication |
| Revocation | Access/refresh revocation, latency SLAs |
| Storage | Consents, authorizations, clients, encrypted secrets |
| Tenancy | Issuer strategy, tenant routing, isolation |
| Risk | Anti-bot, brute force, phishing, token replay, rate limiting |
| Availability | HA, DB replication, caching, key service dependencies |
| Standards | Metadata, OIDC discovery, OAuth2 RFCs, conformance tests |
| Operations | Monitoring, incident response, access reviews, compliance |

Advanced features depend on the threat model: PAR, JAR, mTLS/DPoP sender-constrained tokens, token exchange, FAPI profiles, step-up authentication. Do not enable these features merely because the app is reactive.

## 19. Anti-Patterns and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Self-signing JWTs and calling it an OAuth2 platform | Missing grants, consent, client policies, revocation | Use an IdP or standards-compliant Authorization Server |
| Using ID tokens for APIs | Wrong purpose/audience | Use access tokens |
| Only parsing JWT payloads | Accepts forged claims | Verify signature and claims |
| Verifying signature while skipping `iss`/`aud` | Token confusion | Validate issuer/audience |
| Granting access to all records based on scope alone | IDOR, tenant leakage | Enforce resource-level policies |
| Relaying token A to every service B | Token leakage and wrong audience | Use token exchange/delegation |
| Storing client secrets in SPAs/mobile apps | Secrets get extracted | Use public client + PKCE |
| Disabling CSRF when cookie login exists | CSRF risk | Separate session chains from bearer-only chains |
| Wildcard CORS with credentials | Browser rejection and overly broad trust | Allowlist exact origins |
| Permitting all routes by default | New endpoints may lack protection | Deny by default |
| Every resource server acting as an IdP | Increases complexity and attack surface | Separate roles and ownership |
| Logging bearer/refresh tokens | Token leakage | Redact and manage secrets properly |
| Introspection with no timeout | API hangs when IdP slows down | Add resilience and fail closed |
| Stale JWKS cache | Failures when IdP rotates keys | Configure rotation/cache policies |
| Testing only with `mockJwt` | Misses misconfigured decoders | Add JWT/JWKS/IdP integration tests |
| Blocking security calls on the event loop | Throughput collapses | Use non-blocking calls or bounded schedulers |
| Confusing 401 and 403 | Wrong auth semantics | Separate authentication from authorization |

## 20. Observability by Layer

**WebFlux API Layer:**

- 401/403 counts by route template and client category.
- JWT decode failures by reason: signature, issuer, audience, expiry.
- Introspection latency/errors/timeouts.
- Security rule deny decisions by internal code.
- JWKS refresh/cache failures.
- Downstream token acquisition failures.
- Event-loop saturation and security call latency.

**Authorization Server Layer:**

- Login/MFA successes/failures and suspicious logins.
- Authorization code/token issuance volumes.
- Consent grants/denials.
- Refresh token rotation/reuse events.
- Revocation requests and effective latency.
- Signing key lifecycle events.
- Per-client rate limiting and auditing.

Never use raw tokens, client secrets, PII, or URLs with sensitive queries as log/metric tags. Use correlation IDs free of credentials. When an IdP fails, fail-open authentication is rarely acceptable.

## 21. Implementation Roadmap by Complexity

### Level 1. Protecting a WebFlux API

- Define public/private routes and security chains.
- Choose an authentication mechanism.
- Enforce authorities/scopes, ownership, and tenancy.
- Write 200/401/403 tests.
- Do not issue tokens yourself if an IdP already exists.

### Level 2. Integrating OAuth2/OIDC with an IdP

- Configure issuer, audience, JWKS, or introspection.
- Build OAuth2 client/login if required.
- Define scopes/audiences for downstream APIs.
- Test signature/expiry/issuer/audience validation and key rotation.
- Control CORS/CSRF/cookies, logout, and token handling.

### Level 3. Operating an Authorization Platform

- Design token issuance, grants, and client registration.
- Build consent, refresh/revocation, and signing key lifecycles.
- Implement auditing, tenant isolation, high availability, and backups.
- Run conformance and penetration tests.
- Maintain runbooks for compromised clients/keys/tokens.

Do not jump to Level 3 simply because "the project uses WebFlux". Choose the scope based on the roles you actually need to own.

## 22. Production Checklist

- [ ] Clearly identify whether the app is a resource server, client/login app, or authorization server.
- [ ] Use `SecurityWebFilterChain`/`ServerHttpSecurity` for WebFlux, never Servlet `SecurityFilterChain`.
- [ ] Deny routes without explicit rules by default.
- [ ] Validate JWT signature, issuer, audience, `exp`/`nbf`, and allowed algorithms.
- [ ] Use access tokens for APIs, never ID tokens as substitutes.
- [ ] Map scopes to authorities matching the IdP contract.
- [ ] Enforce ownership/ACL/tenant verification per resource.
- [ ] Configure timeouts, caching, and rotation strategies for JWKS/introspection.
- [ ] Keep private signing keys on the authorization server.
- [ ] Use Authorization Code + PKCE for browser public clients where appropriate.
- [ ] Never embed client secrets in SPAs/native apps.
- [ ] Enforce storage, rotation, reuse detection, and revocation policies for refresh tokens.
- [ ] Match CORS/CSRF/cookie defenses to the authentication model.
- [ ] Never relay bearer tokens to other audiences without an explicit policy.
- [ ] Ensure reactive security calls do not block the event loop.
- [ ] Propagate security context properly through Reactor Context.
- [ ] Test with `mockJwt` for policy and signed-JWT/JWKS/IdP for validation.
- [ ] Include negative tests: expired token, wrong issuer, wrong audience, missing scope.
- [ ] Implement auditing, redaction, incident response, and rate limiting.
- [ ] Give authorization platforms dedicated designs for availability, client lifecycles, and token issuance.

## 23. Self-Check

**Question 1.** Does Spring Security WebFlux automatically become an OAuth2 Authorization Server?

No. It protects APIs and supports OAuth2 resource server, client, and login roles. Token issuance belongs to the authorization server.

**Question 2.** How does `SecurityWebFilterChain` differ from `SecurityFilterChain`?

`SecurityWebFilterChain` belongs to reactive WebFlux; `SecurityFilterChain` belongs to the Servlet security stack.

**Question 3.** How do access tokens and ID tokens differ?

Access tokens are for resource servers; ID tokens are for OIDC clients verifying user identity/login.

**Question 4.** Does having `SCOPE_orders:read` allow reading every order?

No. Ownership/tenant/ACL checks on the specific order are still required.

**Question 5.** What verifies JWTs in WebFlux?

`ReactiveJwtDecoder` with appropriate keys and validators.

**Question 6.** How are opaque tokens validated?

`ReactiveOpaqueTokenIntrospector` calls the authorization server's introspection endpoint.

**Question 7.** Why is audience validation important?

To prevent an access token issued for another API from being accepted by this resource server.

**Question 8.** How do 401 and 403 differ?

401 typically means unauthenticated or invalid token; 403 means authenticated but lacking permissions.

**Question 9.** Is an OAuth2 Client responsible for issuing access tokens?

No. The client requests tokens from the authorization server to access resource servers.

**Question 10.** What does PKCE protect against?

It binds the authorization code to the client that initiated the request, mitigating code interception attacks.

**Question 11.** Does Client Credentials represent a user?

Usually no; it is a grant for a client service's own identity/permissions.

**Question 12.** Why is testing only with `mockJwt` insufficient?

It skips verifying signatures, issuer, audience, and JWKS; real tokens and decoders must also be tested.

**Question 13.** Can CORS replace CSRF protection?

No. CORS is a browser origin policy, whereas CSRF concerns ambient credentials such as cookies.

**Question 14.** Does offline JWT verification revoke tokens immediately upon user logout?

No. Short TTLs or additional revocation/introspection checks aligned with SLAs are needed.

**Question 15.** Why shouldn't private signing keys reside on resource servers?

Resource servers only need public verification keys; issuing tokens belongs to the authorization server.

**Question 16.** When is an in-depth OAuth2 platform needed?

When owning clients, grants, PKCE, consent, JWKS, revocation, multi-tenancy, and HA—rather than merely validating tokens to protect an API.

## 24. Official Documentation and Standards

- [Spring Security — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/): Resource Server, Client, and OAuth2 Login on the reactive stack.
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder`, issuer, JWKS, scopes, and authorities.
- [Spring Security — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): introspection and `ReactiveOpaqueTokenIntrospector`.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/): authorized client manager and `WebClient`.
- [Spring Security — OAuth2 Login WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): authorization-code login.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@PreAuthorize` and Reactor Context.
- [Spring Security — Testing OAuth2](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt`, `WebTestClient`, and policy tests.
- [Spring Security — Authorization Server Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/configuration-model.html): Servlet-oriented authorization server, token endpoints, and OIDC.
- [Spring Boot — OAuth2 Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html): issuer, JWK URI, audiences, and client settings.
- [Spring Boot — Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html): Boot 4 resource-server starter and WebFlux test starter.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): roles and grants.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer tokens used with HTTP APIs.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636): Proof Key for Code Exchange.
- [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint.
- [RFC 7662 — Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): active token introspection.
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token JWT profile.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): threat model and security recommendations.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, authentication, and UserInfo.

**Key Takeaway:** WebFlux security handles authentication/authorization inside the reactive request pipeline. A WebFlux resource server **receives and validates tokens**, an OAuth2 client **requests and uses tokens**, and an authorization server **issues and manages tokens**. In-depth OAuth2 system design is a system-wide problem spanning clients, grants, PKCE, consent, keys, revocation, tenancy, and HA. Even with a valid token, APIs must still enforce permissions on each specific resource.