# Identity Propagation, Token Relay, and Per-Boundary Token Verification

## 1. Real-World Problem in a Multi-Tenant Gateway

A SaaS system has **tenant A** and **tenant B**, each with its own issuer/Identity Provider (IdP). Users log in through **Spring Cloud Gateway Server WebFlux**, and the gateway routes requests to a downstream **Spring WebFlux Resource Server** to read orders. The gateway may hold a WebSession containing an OAuth2 Login Authentication and forward the user's access token downstream via `TokenRelay`.

A configuration that appears to work yet is insufficiently secure is: "Gateway login succeeds, injects `X-User-Id` and `X-Tenant-Id`, and downstream trusts those two headers to read the orders table." If the backend is called directly, a route is misconfigured, or a client deliberately sends those headers itself, the system can leak data across tenants.

This lesson addresses three questions:

1. **What identity crosses each boundary?** Browser session, OAuth2 principal, Bearer access token, service credential, and signed identity assertion are not the same thing.
2. **What does token relay actually forward?** `TokenRelay` sends **the already-issued access token** downstream; it does not re-sign the token, does not change its audience/scope, and does not validate the tenant on its own.
3. **Who is allowed to trust whom?** Every security enforcement point—gateway, downstream API, subsequent service, and data layer—must verify the conditions appropriate to its own boundary.

After this lesson, you will be able to design a trust boundary diagram, distinguish three OAuth2 models, implement WebFlux TokenRelay with OAuth2 Login, verify issuer/audience/tenant/scope downstream, detect spoofed identity headers, run standalone Java 17 policy checks, and build cross-tenant 302/401/403 tests.

**Principle:** authentication at the gateway **does not replace** downstream authentication and authorization. Client-supplied route/hostname/header tenant values **are only context selection hints**, never proof that the user belongs to that tenant.

## 2. Types of Information to Distinguish

| Component | Meaning | How It Is Used |
| --- | --- | --- |
| `SESSION` cookie | Gateway browser session, typically bound to `SecurityContext` | Authenticates browser→gateway; **do not** forward this cookie to every backend |
| `OAuth2AuthenticationToken` | Authentication created after `oauth2Login()` | Tells the gateway which ClientRegistration the user logged in with |
| `OAuth2AuthorizedClient` | Stores `ClientRegistration` and access token, possibly a refresh token | Managed by the Gateway OAuth2 Client; token relay can obtain the access token here |
| OAuth2 **access token** | Credential used to call a resource server | Has `aud`/scope/expiry; verified independently by downstream |
| OIDC **ID Token** | Authentication proof intended for the OAuth2/OIDC client | Does not replace an access token when calling downstream |
| `client_credentials` token | Access token issued to a service/client | Authenticates a **service actor**, does not automatically represent an end user |
| `X-User-Id`, `X-Tenant-Id` | Plain headers, easily spoofed | Treated only as untrusted input unless backed by a dedicated trust contract |
| `iss` | Issuer that signed/issued the access token | Must be in an allowlist and verified |
| `sub` | Subject ID within the issuer's namespace | Not guaranteed unique across multiple issuers |
| `tenant_id` | Application claim issued by the IdP/authorization service | Trust **only after** JWT verification/introspection and when matching the contract |
| `aud` | Target audience/API receiving the token | Downstream must verify it contains its own identity/resource |
| `scope`/`scp` | Granted permission scopes | Spring Security typically maps to `SCOPE_*`; not enough to replace ownership checks |

**An OAuth2 Access Token is a Bearer credential:** if leaked, another party can use it within the token's validity/binding constraints. Therefore, never place tokens in URLs, logs, analytics, error responses, trace headers, or untrusted external APIs.

### 2.1. A JWT proves nothing from its payload alone

Illustrative payload:

~~~json
{
  "iss": "https://idp-a.example/issuer",
  "sub": "user-123",
  "aud": ["orders-api"],
  "tenant_id": "tenant-a",
  "scope": "orders.read",
  "exp": 1790003600
}
~~~

This payload is **not a real signed access token**. Before deriving permissions from `iss`/`tenant_id`/`scope`, Spring Security must verify the JWS signature, trusted algorithm/issuer, `exp`/`nbf` timestamps, and audience. A claim named `tenant_id` inside client-submitted JSON or an unverified JWT **has zero security value**.

If the IdP issues **opaque tokens** instead of JWTs, downstream needs a `ReactiveOpaqueTokenIntrospector` or a validation mechanism supported by the IdP. Never treat an opaque string as a JWT just because it contains dots or is called a "token".

### 2.2. Tenant locator vs. tenant authorization

Request:

~~~http
GET /tenant-b/api/data HTTP/1.1
Host: gateway.example.com
X-Tenant-Id: tenant-b
~~~

The path and header only state **which tenant the client wants to access (tenant-b)**, not whether the user belongs to tenant B. Security rule for this lesson's pattern:

~~~text
routeTenant is configured
AND verifiedJwt.iss == issuerMappedTo(routeTenant)
AND verifiedJwt.tenant_id == routeTenant
AND verifiedJwt.aud contains "orders-api"
AND verified authorities contain "SCOPE_orders.read"
AND requested object belongs to verified tenant/user
~~~

If a user has multiple tenant memberships, a trusted membership source and an active-tenant policy are required; a single `tenant_id` claim cannot be assumed sufficient for every SaaS model.

## 3. Trust Boundaries and Checks at Each Boundary

~~~text
Browser       Edge / WAF         Gateway WebFlux        Orders API        Database
   |              |                   |                    |                 |
   | HTTPS +      |                   |                    |                 |
   | SESSION      |                   |                    |                 |
   |------------->|------------------>|                    |                 |
   |              |            oauth2Login user            |                 |
   |              |            OAuth2AuthorizedClient      |                 |
   |              |            TokenRelay=                 |                 |
   |              |                   |                    |                 |
   |              |                   | Authorization:     |                 |
   |              |                   | Bearer accessToken |                 |
   |              |                   |------------------->|                 |
   |              |                   |              JWT / introspection     |
   |              |                   |              iss, exp, aud           |
   |              |                   |              tenant, scope          |
   |              |                   |                    | tenant-scoped    |
   |              |                   |                    | query + ownership|
   |              |                   |                    |---------------->|
   |              |                   |                    |<----------------|
   |<-------------|<------------------|<-------------------|                 |
~~~

| Boundary | What to Verify | What Never to Do |
| --- | --- | --- |
| Browser → Edge | TLS, canonical host, traffic controls, request size, forwarded-header sanitization | Trust `X-Forwarded-*` sent directly by an Internet client |
| Edge → Gateway | Trusted proxy; OAuth2 Login/callback, WebSession, Secure/HttpOnly/SameSite cookies, CSRF | Let raw external identity headers become the principal |
| Gateway → Orders | Fixed route URI, TLS/mTLS, token relay with the right access token, outbound host restrictions | Forward refresh tokens, ID Tokens, or Bearer tokens to user-controlled URLs |
| Orders authentication | JWT signature/JWKS or opaque introspection, issuer allowlist, `aud`, `exp`/`nbf` | Treat "arriving from a private network" as already authenticated |
| Orders authorization | Verified tenant claim + route tenant, issuer per tenant, scopes/roles | Rely on self-declared path/header to grant tenant access |
| Orders → DB | Tenant predicate, row-level security, or membership/ownership | Filter only by object ID while forgetting tenant |
| Orders → third service | Appropriate credential for the new audience, service identity/OBO, and audit actor | Arbitrarily reuse every user access token across all microservices |
| Response → client | Proper 401/403/302 per flow, no secret leakage | Echo tokens or raw JWT claims in error responses |

Each boundary can have its own TLS/service identity. The internal network is not unconditionally trustworthy: a compromised service or a direct-to-backend route breaks the assumption that "only the Gateway calls the backend".

## 4. Three Credential-Forwarding Models — Never Mix Them Up

### 4.1. Browser OAuth2 Login → TokenRelay user access token

~~~text
Browser -- SESSION cookie --> Gateway (oauth2Login)
                                  |
                                  | User's OAuth2AuthorizedClient
                                  | access token issued by IdP
                                  v
                             TokenRelay=
                                  |
                                  | Authorization: Bearer <user access token>
                                  v
                         Orders Resource Server
                                  |
                           verify aud/iss/tenant/scope
~~~

This is the use case documented by Spring Cloud Gateway Server WebFlux: `TokenRelay=` (without arguments) forwards the access token of the authenticated OAuth2 Login user. The browser never has to hold the access token in JavaScript. The refresh token (if any) stays managed by the Gateway OAuth2 Client and is not sent to the Orders API.

**Hardest prerequisite:** The IdP must issue an access token **intended for Orders**. A successful Gateway login does not mean the access token has `aud=orders-api`. An access token meant only for UserInfo or `gateway-api` must be rejected by Orders.

### 4.2. Machine/mobile sends Bearer to a Gateway Resource Server

~~~text
Mobile --> Gateway: Authorization: Bearer token
                    |
             Gateway validates bearer token
                    |
        explicit delegation strategy:
        - forward only if downstream is valid audience
        - token exchange for downstream audience
        - or derive signed internal assertion
                    |
                    v
             Downstream validates again
~~~

By default, this is not the same flow as `oauth2Login()`. `TokenRelay=` in an OAuth2 Client configuration must not be naively assumed to mean "any incoming Bearer header is automatically relayed." If the Gateway acts as both a Resource Server and a caller to downstream services, you must explicitly define how forwarding/exchange works based on the verified incoming Authentication, where authorized clients are stored, and which audience the token carries.

Simply copying the `Authorization` header from the incoming request to downstream **without verifying token, tenant, route, and audience** can turn the gateway into a forward proxy leaking or misrouting an attacker's credentials.

### 4.3. `TokenRelay=service-client` differs from user identity

~~~yaml
filters:
  - TokenRelay=service-client
~~~

When `service-client` is a `client_credentials` registration, the token is issued to **the service**. Downstream sees the service principal; it does not automatically know which user Alice initiated the request.

If downstream needs to act "on behalf of Alice," there must be a delegation/OBO model and auditing that separates the **actor service** from the **subject end user**. Injecting `X-User: Alice` alongside a service token does not make Alice an authenticated subject.

### 4.4. Token exchange when audiences differ

If the gateway holds a token with `aud=gateway-api` while Orders requires `aud=orders-api`, you can use **OAuth2 Token Exchange (RFC 8693)** if the Authorization Server supports it:

~~~text
User token: aud=gateway-api
      |
Gateway authenticates token + user/tenant
      |
RFC 8693 exchange / on-behalf-of
      |
New access token: aud=orders-api; narrow scope=orders.read
      |
Orders verifies new signature, issuer, audience, tenant and scope
~~~

`TokenRelay` **does not perform** token exchange automatically. Never alter a JWT payload's `aud` yourself or sign a token "looking like the IdP" using an application key. If the IdP does not support RFC 8693, design another explicitly verified delegation contract or adjust the token issuance policy.

## 5. Spring Cloud Gateway WebFlux TokenRelay in Practice

### 5.1. Route factory

Official syntax in Spring Cloud Gateway Server WebFlux:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders
              uri: http://localhost:9000
              predicates:
                - Path=/api/orders/**
              filters:
                - TokenRelay=
~~~

`TokenRelay=` retrieves the access token from the OAuth2 Login authenticated user if a matching authorized client exists. For a specific registration, you can write `TokenRelay=my-client-registration`. Equivalent Java DSL:

~~~java
@Bean
RouteLocator routes(RouteLocatorBuilder builder) {
    return builder.routes()
            .route("orders", r -> r.path("/api/orders/**")
                    .filters(f -> f.tokenRelay())
                    .uri("http://localhost:9000"))
            .build();
}
~~~

These are two **mutually exclusive alternative snippets**; do not register the same route twice. `localhost:9000` is for local development only; production requires HTTPS/mTLS/trusted service DNS and outbound restrictions.

### 5.2. Requirements for the factory to work

- Spring Cloud Gateway Server **WebFlux** starter, not MVC Gateway.
- Spring Security OAuth2 Client dependency and at least one valid ClientRegistration.
- `ReactiveClientRegistrationRepository` created by Boot from `spring.security.oauth2.client.*`.
- For browser login, `oauth2Login()` has completed and the authorized client holds an access token.
- The token is issued for the right downstream audience, issuer, scope, and tenant.
- `ReactiveOAuth2AuthorizedClientService` or `ServerOAuth2AuthorizedClientRepository` stores state in the matching context.
- With multiple replicas, note that the default authorized client storage may be **in-memory**; production may require a shared secure store and refresh coordination.

### 5.3. What TokenRelay does NOT do on its own

`TokenRelay` does not automatically:

1. Change the audience or scope of an access token.
2. Convert an ID Token into an access token for downstream.
3. Verify the JWT on behalf of every target resource server.
4. Check whether the user is allowed to access the tenant in the path.
5. Create a signed identity header with a trusted issuer.
6. Implement RFC 8693/token exchange.
7. Revoke issued access tokens at the IdP when logging out of the gateway.
8. Guarantee that every downstream 401 triggers an immediate refresh without error handling.
9. Distinguish a service token from end-user delegation for auditing.

These limitations must be documented in the architecture contract; the name "TokenRelay" easily misleads learners into thinking the gateway mints an identity trusted by all downstream services.

## 6. Header Spoofing and Confused Deputy

### 6.1. Merely injecting `X-User` downstream is not enough

Spoofed request:

~~~http
GET /tenant-b/api/orders HTTP/1.1
Host: gateway.example.com
X-User-Id: admin
X-Tenant-Id: tenant-b
~~~

If the backend trusts these two headers without verifying their origin, a client can impersonate admin. Even if the gateway injects the header properly, an attacker may still find a direct-to-backend path or exploit another internal service. You must **strip client-controlled identity headers** at the edge/gateway and use a Bearer token or a **signed identity assertion** verified by downstream (issuer, signature, audience, expiry, tenant), along with service-to-service TLS/mTLS/network policies where required.

**Do not** trust a signed assertion just because it sits in a special header: downstream still needs to know which keys are valid, who is allowed to issue assertions, its own audience, and the TTL. Some systems place trust in a service mesh/gateway using mTLS and workload identities, but that trust contract must be explicitly designed and tested—never implicitly inferred from a private IP.

### 6.2. Confused deputy

Suppose the Gateway holds a broad `orders.admin` service token, while a tenant A user only has `orders.read`. If the gateway calls `/tenant-b/admin/export` using the service token on the user's behalf and downstream sees only the admin service, that can become a **confused deputy** vulnerability leading to cross-tenant leakage.

Mitigate the risk by:

- Using user-delegated access tokens with narrow scopes and audiences, or token exchange/OBO.
- Never reusing a privileged service token across all user-facing routes.
- If a service token is mandatory, preserving verified actor + subject context and enforcing delegation rights downstream.
- Enforcing tenant + object ownership/row isolation at the data layer.
- Auditing the actor service, subject user, tenant, action, and correlation ID under a trusted contract.

### 6.3. Never forward cookies or Authorization to arbitrary hosts

Anti-pattern example:

~~~java
// DO NOT USE: destination URL comes from an external request.
String target = exchange.getRequest()
        .getQueryParams().getFirst("target");
webClient.get().uri(target)
        .headers(headers -> headers.setBearerAuth(accessToken));
~~~

This is only an **SSRF/token exfiltration warning snippet**, not a standalone method. The Gateway should enforce a route/backend allowlist and never place refresh tokens, session cookies, or Authorization headers into logs or redirect them to untrusted domains. Avoid enabling `setDefaultOAuth2AuthorizedClient(true)` on a WebClient used for arbitrary URLs.

## 7. Multi-tenancy: Verifying Issuer, Audience, Tenant, and Scope

### 7.1. The issuer in an unverified JWT is only input for selecting a decoder

A JWT contains an `iss` claim, but before verification, an attacker can modify the payload. Spring Security WebFlux's `JwtIssuerReactiveAuthenticationManagerResolver` can inspect `iss` to **select** a `ReactiveAuthenticationManager`, but the selection must be restricted to a **trusted issuer allowlist**. The selected manager must then verify the signature and claims to produce an authenticated principal.

~~~java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver
                .fromTrustedIssuers(
                        "https://idp-a.example/issuer",
                        "https://idp-b.example/issuer");
~~~

And wire it in:

~~~java
.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver))
~~~

These are **WebFlux snippets**, not standalone code. Never build a JWK URL dynamically from an arbitrary token `iss`, as an attacker could stand up an issuer they control, leading to false authentication or SSRF.

### 7.2. A token with a valid issuer can still target the wrong tenant

Suppose both issuer A and issuer B are valid. Token A may verify successfully through manager A, yet the client calls `/tenant-b/api/orders`. If authorization only checks `authenticated()`, token A could enter route B. Therefore, you must **match the verified issuer, tenant claim, route tenant, scope, and audience**, not just the issuer allowlist.

This example model assumes 1 tenant ↔ 1 issuer. A system with 1 issuer serving multiple tenants must switch to appropriate membership/tenant claim validation; a system where one tenant trusts multiple issuers needs a richer trust policy. Never assume 1-to-1 if the business contract differs.

### 7.3. Audience is checked at every API

~~~json
{
  "iss": "https://idp-a.example/issuer",
  "sub": "employee-123",
  "tenant_id": "tenant-a",
  "aud": ["gateway-api"],
  "scope": "orders.read"
}
~~~

The token above has a valid-looking issuer and scope, but **the Orders Resource Server requires aud=orders-api**. If the audience validator rejects this token during authentication, the status is typically **401**, not "Gateway login failed." The IdP must issue an access token with the right audience, or token exchange must be used.

### 7.4. Roles and tenant membership do not automatically derive from scope

`scope=orders.read` typically becomes `SCOPE_orders.read`. However, this scope only states a coarse capability granted to the token; it does not prove the user is allowed to read all orders of tenant A or tenant B. The endpoint must still check tenant and object ownership. Never blindly map any `"admin"` string to `ROLE_ADMIN` without an IdP contract/allowlist.

## 8. Standalone Java 17: Checking Policy After Token Verification

The example below is a **pure Java program** requiring no Spring or IdP. It assumes a `VerifiedIdentity` already verified by the authentication layer. It checks only issuer/tenant/audience/scope logic and **must not be used to parse unverified JWTs**.

Create `BoundaryDecisionDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public final class BoundaryDecisionDemo {
    enum Decision {
        ALLOW, UNAUTHENTICATED, UNKNOWN_ROUTE,
        UNTRUSTED_ISSUER, WRONG_AUDIENCE,
        TENANT_MISMATCH, FORBIDDEN
    }

    record VerifiedIdentity(
            String issuer,
            String tenant,
            Set<String> audiences,
            Set<String> authorities) {
    }

    private static final Map<String, String> ISSUERS = Map.of(
            "tenant-a", "https://idp-a.example/issuer",
            "tenant-b", "https://idp-b.example/issuer");

    private BoundaryDecisionDemo() {
    }

    static Decision decide(
            String requestedTenant, VerifiedIdentity verified) {

        String expectedIssuer = ISSUERS.get(requestedTenant);
        if (expectedIssuer == null) {
            return Decision.UNKNOWN_ROUTE;
        }
        if (verified == null) {
            return Decision.UNAUTHENTICATED;
        }
        if (!expectedIssuer.equals(verified.issuer())) {
            return Decision.UNTRUSTED_ISSUER;
        }
        if (!verified.audiences().contains("orders-api")) {
            return Decision.WRONG_AUDIENCE;
        }
        if (!requestedTenant.equals(verified.tenant())) {
            return Decision.TENANT_MISMATCH;
        }
        if (!verified.authorities().contains("SCOPE_orders.read")) {
            return Decision.FORBIDDEN;
        }
        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        VerifiedIdentity good = new VerifiedIdentity(
                "https://idp-a.example/issuer", "tenant-a",
                Set.of("orders-api"), Set.of("SCOPE_orders.read"));

        VerifiedIdentity wrongTenant = new VerifiedIdentity(
                good.issuer(), "tenant-b",
                good.audiences(), good.authorities());

        VerifiedIdentity wrongAudience = new VerifiedIdentity(
                good.issuer(), good.tenant(),
                Set.of("gateway-api"), good.authorities());

        VerifiedIdentity noScope = new VerifiedIdentity(
                good.issuer(), good.tenant(),
                good.audiences(), Set.of());

        VerifiedIdentity wrongIssuer = new VerifiedIdentity(
                "https://untrusted.example/issuer", good.tenant(),
                good.audiences(), good.authorities());

        System.out.println("good_a="
                + decide("tenant-a", good));
        System.out.println("a_token_on_b="
                + decide("tenant-b", good));
        System.out.println("wrong_tenant_claim="
                + decide("tenant-a", wrongTenant));
        System.out.println("wrong_audience="
                + decide("tenant-a", wrongAudience));
        System.out.println("missing_scope="
                + decide("tenant-a", noScope));
        System.out.println("unknown_issuer="
                + decide("tenant-a", wrongIssuer));
        System.out.println("no_principal="
                + decide("tenant-a", null));
        System.out.println("unknown_route="
                + decide("tenant-x", good));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac BoundaryDecisionDemo.java
java BoundaryDecisionDemo
~~~

**Deterministic stdout from source:**

~~~text
good_a=ALLOW
a_token_on_b=UNTRUSTED_ISSUER
wrong_tenant_claim=TENANT_MISMATCH
wrong_audience=WRONG_AUDIENCE
missing_scope=FORBIDDEN
unknown_issuer=UNTRUSTED_ISSUER
no_principal=UNAUTHENTICATED
unknown_route=UNKNOWN_ROUTE
~~~

The decisions above are **not HTTP status codes**. In a real application, signature/issuer/audience failures during authentication typically return 401; authenticated users lacking permissions/wrong tenant typically get 403; unknown routes may return 404 per policy. This model does not replace a JWT decoder, OIDC token exchange, or database membership checks.

## 9. Integration Example: Two Spring Boot WebFlux Applications

We build two local Maven projects:

- `gateway-app` — Spring Boot **4.1.2**, Spring Cloud **2025.1.2**, Spring Cloud Gateway Server WebFlux, OAuth2 Client Login + TokenRelay, port **8080**.
- `orders-service` — Spring Boot **4.1.2**, Spring Security reactive Resource Server JWT, port **9000**, independently verifying two issuers with audience `orders-api` and tenant-aware policy.

Spring Cloud 2025.1.2 supports Spring Boot 4.1.x. Spring Boot 4 renamed the OAuth2 Client/Resource Server starters to `spring-boot-starter-security-oauth2-client` and `spring-boot-starter-security-oauth2-resource-server`; do not copy legacy names from an old Gateway snippet and assume they are standard Boot 4 starters.

**External prerequisite:** requires real IdPs with HTTPS OIDC discovery, two OAuth2 ClientRegistrations, and JWT access tokens intended for `orders-api`. This is integrable application configuration source, **not a self-starting mock IdP**. The pure Java section above runs completely without an IdP.

### 9.1. Gateway pom.xml

Create `gateway-app/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>gateway-app</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.1.2</spring-cloud.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
        </dependency>
    </dependencies>
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>
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

### 9.2. Gateway application.yml

Create `gateway-app/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: tenant-a-orders
              uri: http://localhost:9000
              predicates:
                - Path=/tenant-a/api/**
              filters:
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=X-User-Id
                - RemoveRequestHeader=X-Tenant-Id
                - TokenRelay=
            - id: tenant-b-orders
              uri: http://localhost:9000
              predicates:
                - Path=/tenant-b/api/**
              filters:
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=X-User-Id
                - RemoveRequestHeader=X-Tenant-Id
                - TokenRelay=

  security:
    oauth2:
      client:
        registration:
          corp-a:
            provider: issuer-a
            client-id: ${A_CLIENT_ID}
            client-secret: ${A_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,orders.read
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
          corp-b:
            provider: issuer-b
            client-id: ${B_CLIENT_ID}
            client-secret: ${B_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,orders.read
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          issuer-a:
            issuer-uri: ${A_ISSUER}
          issuer-b:
            issuer-uri: ${B_ISSUER}
~~~

When saving this lesson, the `$` sign in YAML is converted into a plain dollar sign for **Spring property placeholders** (`$...`). These variables must be provided by the environment/secret manager; they are not pre-existing dummy credentials.

- `TokenRelay=` retrieves the access token of the OAuth2 Login session corresponding to the current user.
- `RemoveRequestHeader=Authorization` before relay avoids blindly forwarding a client-supplied header; the OAuth2 Client filter then injects the token if resolved.
- Identity headers sent by the client are also stripped. Orders does not rely on these headers.
- The `/tenant-a/api/**` or `/tenant-b/api/**` path is preserved; downstream uses the path as the requested tenant.
- Both routes point to the fixed URI `http://localhost:9000` for local use only. Production requires HTTPS/mTLS, network policies, and a backend allowlist.
- The Gateway **does not automatically switch the user login provider by path**. A user logged in via corp-a can try the tenant-b path; downstream must reject it.
- `ClientRegistration` requires an IdP with real issuer metadata and accurately registered callbacks.

### 9.3. GatewayApplication.java

Create `gateway-app/src/main/java/com/example/gateway/GatewayApplication.java`:

~~~java
package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@SpringBootApplication
@EnableWebFluxSecurity
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain gatewaySecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

`oauth2Login()` manages redirects, state/callback, and creates the authenticated user. OAuth2AuthorizedClient holds the access token; the TokenRelay route attaches the Bearer token for downstream. Never disable CSRF globally just because the gateway serves JSON: cookie-backed browser requests with POST/PUT/DELETE still need an explicit CSRF threat model.

### 9.4. Orders pom.xml

Create `orders-service/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
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

This is a **Resource Server** receiving Bearer tokens; it does not need OAuth2 ClientRegistrations to perform OAuth2 Login.

### 9.5. Orders application.properties

Create `orders-service/src/main/resources/application.properties`:

~~~properties
server.port=9000
tenants.a.issuer=${A_ISSUER}
tenants.b.issuer=${B_ISSUER}
orders.audience=orders-api
~~~

The issuer must be a real, trusted HTTPS IdP. Tokens issued by the IdP must carry `aud=orders-api` and `tenant_id=tenant-a` or `tenant-b` per contract. If the provider does not issue a tenant claim, the sample code proactively denies the route rather than guessing from the path.

### 9.6. OrdersApplication.java — Verifying at Each Boundary

Create `orders-service/src/main/java/com/example/orders/OrdersApplication.java`:

~~~java
package com.example.orders;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            @Value("${tenants.a.issuer}") String issuerA,
            @Value("${tenants.b.issuer}") String issuerB,
            @Value("${orders.audience}") String audience) {

        Map<String, ReactiveAuthenticationManager> managers = Map.of(
                issuerA, jwtManager(issuerA, audience),
                issuerB, jwtManager(issuerB, audience));

        var resolver = new JwtIssuerReactiveAuthenticationManagerResolver(
                issuer -> Mono.justOrEmpty(managers.get(issuer)));

        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/tenant-a/api/data")
                                .access(tenantAccess("tenant-a", issuerA))
                        .pathMatchers("/tenant-b/api/data")
                                .access(tenantAccess("tenant-b", issuerB))
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.authenticationManagerResolver(resolver))
                .build();
    }

    private static ReactiveAuthenticationManager jwtManager(
            String issuer, String audience) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
                        .build();

        OAuth2TokenValidator<Jwt> audValidator =
                jwt -> jwt.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error("invalid_token",
                                        "Wrong audience for orders", null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(issuer),
                        audValidator));

        return new JwtReactiveAuthenticationManager(decoder);
    }

    private static ReactiveAuthorizationManager<AuthorizationContext>
            tenantAccess(String expectedTenant, String expectedIssuer) {

        return (authentication, context) ->
                authentication.map(auth -> {
                    if (!(auth instanceof JwtAuthenticationToken jwtAuth)
                            || !auth.isAuthenticated()) {
                        return new AuthorizationDecision(false);
                    }

                    Jwt jwt = jwtAuth.getToken();

                    boolean issuerOk = jwt.getIssuer() != null
                            && expectedIssuer.equals(
                                    jwt.getIssuer().toString());

                    boolean tenantOk = expectedTenant.equals(
                            jwt.getClaimAsString("tenant_id"));

                    boolean scopeOk = auth.getAuthorities().stream()
                            .map(GrantedAuthority::getAuthority)
                            .anyMatch("SCOPE_orders.read"::equals);

                    return new AuthorizationDecision(
                            issuerOk && tenantOk && scopeOk);
                }).defaultIfEmpty(new AuthorizationDecision(false));
    }

    @RestController
    static class OrdersController {

        @GetMapping(value = {
                "/tenant-a/api/data",
                "/tenant-b/api/data"
        }, produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> data(
                @AuthenticationPrincipal Jwt jwt) {

            return Mono.just(Map.of(
                    "result", "ORDERS_OK",
                    "tenant", jwt.getClaimAsString("tenant_id")));
        }
    }
}
~~~

**What is checked where?**

- `JwtIssuerReactiveAuthenticationManagerResolver` reads `iss` as **input to select a manager**. `managers` contains only two trusted issuers; it never fetches metadata from an arbitrary rogue issuer.
- `NimbusReactiveJwtDecoder` fetches trusted JWKS/keys and verifies the signature. `JwtValidators.createDefaultWithIssuer` verifies the issuer and timestamps. `audValidator` ensures the token is meant for `orders-api`; audience errors typically return **401**.
- `tenantAccess` is a post-authentication `ReactiveAuthorizationManager`. It checks that issuer A/B matches the route, checks `tenant_id` in the verified JWT, and checks `SCOPE_orders.read`. If an authenticated user has the wrong tenant/scope, it typically returns **403**.
- `anyExchange().denyAll()` denies any unlisted route; there is no "default permitAll."
- The controller reads `@AuthenticationPrincipal Jwt` from the Security Context; it never reads identity from `X-User-Id` or `X-Tenant-Id`.
- With a real database, you must still verify order ownership and run tenant-scoped queries. The demo returns static results and therefore only illustrates the authentication/authorization boundary.

**Startup note:** `withIssuerLocation(issuer)` needs trusted issuer metadata/JWK Set; depending on the implementation/version, it may contact the IdP while building the decoder, so do not expect the app to start end-to-end with two placeholder URLs. In multi-issuer production deployments, you can build managers lazily or specify a trusted JWK Set URI directly; still keep the issuer/audience validators.

### 9.7. Why use a resolver instead of two match-all JWT chains?

Two `SecurityWebFilterChain` beans that both match every request easily suffer from unintended ordering issues. A resolver selects the manager by trusted issuer within a single chain, and then policy enforces the **route tenant**. When you need to split browser and API routes, use deliberate security matchers/order; never mix Servlet `HttpSecurity` into WebFlux.

## 10. Running the Demo with Provisioned IdPs

### 10.1. Preparation

You need:

1. JDK 17+, Maven or wrapper.
2. Two real HTTPS OIDC issuers with JWT verification keys.
3. OAuth2 client registrations `corp-a`, `corp-b` with confidential client credentials and redirect URIs:
   - `http://localhost:8080/login/oauth2/code/corp-a`
   - `http://localhost:8080/login/oauth2/code/corp-b`
4. Real access tokens with `aud=orders-api`, `scope=orders.read`, and `tenant_id` matching the schema.
5. Gateway on port 8080, Orders on port 9000; local HTTP proxying is **for dev only**.
6. Production: HTTPS + trusted proxy/forwarded headers, secure cookies, mTLS/network policy where needed.

Without real IdPs, real tokens, and callback registrations, you can only run `BoundaryDecisionDemo` offline; you should not claim to have completed OAuth2/login protocol tests.

### 10.2. Orders Service

In Bash, inside the `orders-service` directory:

~~~bash
export A_ISSUER='https://real-idp-a.example/issuer'
export B_ISSUER='https://real-idp-b.example/issuer'
./mvnw clean package
./mvnw spring-boot:run
~~~

These are **example values**; replace them with real issuers. If you do not have the Maven wrapper, use `mvn`. In PowerShell, use `$env:A_ISSUER="..."` and `.\mvnw.cmd spring-boot:run`.

### 10.3. Gateway

In another terminal, inside `gateway-app`:

~~~bash
export A_CLIENT_ID='gateway-client-a'
export A_CLIENT_SECRET='secret-from-idp-a'
export A_ISSUER='https://real-idp-a.example/issuer'

export B_CLIENT_ID='gateway-client-b'
export B_CLIENT_SECRET='secret-from-idp-b'
export B_ISSUER='https://real-idp-b.example/issuer'

./mvnw clean package
./mvnw spring-boot:run
~~~

Never commit real secrets to Git or documentation; use a secret manager in production. Client registrations must be permitted by the IdP to receive **access tokens intended for orders-api**, not only ID Tokens/OIDC userinfo.

### 10.4. Browser tenant A

In browser profile A:

1. Open `http://localhost:8080/oauth2/authorization/corp-a`.
2. Log in to IdP A and complete the callback; the Gateway stores the WebSession.
3. Open `http://localhost:8080/tenant-a/api/data`.
4. The Gateway uses `TokenRelay=` to forward the access token from the authorized client to Orders.
5. Orders verifies signature/issuer/audience, checks tenant and scope; if valid, returns **200** with JSON:

~~~json
{
  "result": "ORDERS_OK",
  "tenant": "tenant-a"
}
~~~

6. In the **same profile**, open `/tenant-b/api/data`: token A does not match tenant B's issuer/tenant, so Orders **rejects** it, typically with **403**.
7. Use an **independent browser profile B** and log in via `corp-b` to test tenant B.

If IdP A issues a token with `aud=gateway-api` instead of `orders-api`, Orders rejects it with **401** — that is the right policy. If the token lacks `SCOPE_orders.read`, Orders rejects it with **403**. Never remove audience or tenant checks just to make a demo return 200.

### 10.5. Testing the Resource Server Directly

In a local/trusted test environment when you have a real token:

~~~bash
curl -i -H "Authorization: Bearer $TENANT_A_ACCESS_TOKEN" \
  http://localhost:9000/tenant-a/api/data

curl -i -H "Authorization: Bearer $TENANT_A_ACCESS_TOKEN" \
  http://localhost:9000/tenant-b/api/data
~~~

The first request can return 200 if claims are complete; the second must be rejected. Without a token, the backend must never trust caller-supplied headers. **Never** put real tokens into committed scripts, logs, or public terminal transcripts.

### 10.6. Calling the authorization endpoint with curl is not a complete login

~~~bash
curl -i http://localhost:8080/oauth2/authorization/corp-a
~~~

The command typically shows a redirect to the IdP, but `curl` does not automatically complete Authorization Code, state/nonce, cookies, callbacks, and token exchange. You need a browser profile or a full OIDC integration test harness.

## 11. Per-Boundary Test Matrix

| Scenario | Expected Behavior |
| --- | --- |
| Anonymous browser hits private Gateway route | 302 login redirect (browser flow) |
| Browser logged into A hits route A with valid claims | Relays token A, downstream 200 |
| Browser logged into A hits route B | Downstream 403 due to wrong issuer/tenant route |
| Browser logged into B hits route B | Downstream 200 when claims are valid |
| Client spoofs `X-User-Id: admin` | Header stripped/ignored; no admin privilege granted |
| Client spoofs `X-Tenant-Id: tenant-b` with token A | No access to tenant B |
| Missing Bearer on Orders private endpoint | 401 |
| Wrong JWT signature or key not from issuer | 401 |
| Issuer outside allowlist | 401; never queries unknown issuer's JWKS |
| JWT `aud=gateway-api` | 401 at Orders |
| Expired JWT or future `nbf` | 401 |
| Valid token missing `orders.read` | 403 |
| Valid token with `tenant_id` differing from path | 403 |
| Token with valid tenant/scope but order ID belongs to another user | Business/data policy must deny |
| Backend called bypassing Gateway | Still verifies Bearer independently; never trusts private IP |
| Attacker-controlled route target | Gateway must never relay tokens there |
| TokenRelay uses service client_credentials | Downstream treats it as a service actor |
| Access token revoked / logout | Requires dedicated token lifecycle policy; never assume cookie logout revokes tokens |
| JWT signed with new key | JWKS refresh/rotation per policy; never skip signature checks |
| Downstream 401/403 | Distinguish authentication vs. authorization; never retry infinitely |
| Gateway missing OAuth2AuthorizedClient | Never synthesize fake user/token |
| Public JSON API and browser login share gateway | Choose entry points/chains for 401 vs. 302 |

### 11.1. WebTestClient does not prove JWT signatures

Reactive Spring Security Test provides `mockJwt()` for testing authorization. Example snippet:

~~~java
// Test snippet: requires WebTestClient configured with SecurityMockServerConfigurers.
webTestClient.mutateWith(mockJwt()
        .jwt(jwt -> jwt.claim("tenant_id", "tenant-a"))
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.read")))
        .get().uri("/tenant-a/api/data")
        .exchange()
        .expectStatus().isOk();
~~~

This is **not a standalone JUnit class**. `mockJwt()` injects a fake Authentication and typically bypasses the JWT decoder, so it **does not test** signature/`aud`/issuer JWKS. You must have tests with tokens signed by a test private key + a fake OIDC issuer that actually run the resolver/decoder. For Gateway TokenRelay, also test with a fake OAuth2 Login/AuthorizedClient and a mock HTTP downstream to verify that the Bearer header is attached properly and spoofed headers are stripped.

### 11.2. Testing with two browser profiles

Use separate browser profiles A and B with isolated cookies/local storage, never sharing the same OAuth2 session. After logging into A:

- Inspect network traffic: the browser only sends `SESSION` to the Gateway, and **never** needs to hold the refresh token in the browser.
- Gateway outbound requests to Orders carry the Bearer access token without requiring raw session cookies for Orders.
- Client-controlled headers `X-User-Id`/`X-Tenant-Id` do not determine Authentication at Orders.
- Token A on route B must be denied; this is the most critical test of the parent topic "Gateway and Multi-tenancy".

### 11.3. Testing failures and token lifecycle

If downstream returns 401 `invalid_token`, the gateway needs a strategy to detect stale authorized clients, refresh/re-login, and handle failures appropriately. `ServerOAuth2AuthorizedClientExchangeFilterFunction` has a failure handler, though **behavior depends on the constructor**; never assume Gateway TokenRelay handles every cleanup/retry automatically. If downstream returns 403 for a missing scope, refreshing the token will not grant new permissions. Never use `retryWhen(Retry.indefinitely())`; side-effecting POSTs need an idempotency contract before retrying.

## 12. HTTP Statuses and Security Semantics

| Status | Typical Source | Meaning |
| --- | --- | --- |
| 302 | Gateway `oauth2Login()` | Anonymous browser redirected to login |
| 401 | Resource Server JWT/opaque authentication | Missing/invalid/expired/wrong-audience Bearer |
| 403 | Gateway or Orders authorization | Authenticated but missing scope, tenant, or membership |
| 404 | Gateway route or business lookup | Route does not exist; may be used to avoid revealing resources |
| 429 | Edge/Gateway/Orders/IdP | Rate limit; do not assume token was revoked |
| 502/503 | Gateway/Orders/upstream/IdP outage | Infrastructure failure, not missing user role |

An app serving browser sessions and mobile APIs together may need **two security chains/entry points** with clear matchers so mobile receives JSON 401 instead of an HTML login redirect. Never copy an `oauth2Login()` configuration to a Bearer-only backend API.

## 13. Multi-Tenancy Pitfalls

### 13.1. Tenant does not always equal issuer

One issuer can issue tokens for multiple tenants; one tenant can also trust multiple IdPs. The demo deliberately uses 1:1 for ease of testing. When a product has different membership rules:

- Separate `issuer allowlist` from `tenant membership policy`.
- Verify the selected active tenant and the user's permissions within that tenant.
- Link identities by `issuer + subject` or a verified stable internal user ID.
- Never merge users solely by email or by a bare `sub` without the issuer.
- Cache permissions keyed by tenant+issuer+subject+audience with a TTL/revocation contract.

### 13.2. IDOR after the tenant check passes

A valid token A on route A does not grant permission to read orders belonging to **every user** in tenant A. Repositories must query by verified tenant and object ownership/membership, such as `WHERE tenant_id = :tenant AND order_id = :id`, then verify read permissions per account/team/role. Never use `tenant_id` from a JSON request body as the sole filter.

### 13.3. Multi-audience JWTs increase blast radius

A token carrying audiences for gateway, Orders, Billing, and Admin expands exposure if leaked. Prefer narrow audiences and scoped tokens, exchanging tokens across boundaries where needed. Correct audience at downstream is a **mandatory check**, not an "optional optimization".

### 13.4. Logout does not automatically revoke downstream tokens

When the Gateway clears a WebSession, the browser can no longer use that session, but previously issued access tokens may remain valid at Orders until `exp`/revocation. With local JWT verification, Orders does not automatically observe logout events. For early revocation requirements, use short TTLs, introspection, denylists, session/token versioning, or a dedicated online policy.

### 13.5. A broad service token cannot replace every end-user token

A Gateway holding a broad-scoped service client_credentials token must not implicitly turn into end-user authority. When acting on behalf of a user, implement a delegation/OBO protocol, actor/subject auditing, tenant isolation, and downstream policy enforcement. Never simply append an `X-User` header to a service Bearer token.

## 14. Production Security and Operations

### 14.1. TLS and Forwarded headers

- TLS/HTTPS from client to edge/gateway; backend HTTPS/mTLS if the threat model requires it.
- Trust `Forwarded`/`X-Forwarded-Proto`/`X-Forwarded-Host` only from operator-managed proxies that strip external headers.
- Never use an unnormalized request `Host` as an issuer/JWKS URL or arbitrary redirect URI.
- Restrict backend network policies to reduce Gateway bypass risk.
- Gateway browser cookies need `Secure`, `HttpOnly`, and appropriate `SameSite`; keep CSRF for unsafe cookie-backed requests.
- CORS does not replace authentication/authorization; never enable credentialed CORS for all origins.

### 14.2. OAuth2AuthorizedClient storage and rotation

TokenRelay can use the default in-memory store on a single instance. Multi-node setups require evaluating session persistence, secure shared storage, refresh token rotation concurrency, outages, and cleanup. Because the store may contain refresh tokens/secrets, it must be encrypted and access-controlled. Never log `Authorization` or raw JWTs/ID Tokens/userinfo.

### 14.3. Impact of key rotation and token revocation

JWT Resource Servers cache trusted public keys. Key rotation requires valid JWKS refreshes; never disable signature checks when encountering an unknown `kid`. Local JWT validation may continue accepting unexpired tokens after revocation unless online status checks are present. Audit events/permission changes need an explicit SLA. With opaque tokens, the introspection endpoint sits on the critical path with network failure/caching tradeoffs.

### 14.4. Rate limiting and tenant fairness

Gateway/Orders must defend against request bursts, malformed tokens, and authentication manager discovery storms. Never fetch untrusted issuer JWKS from a token. Track QPS/latency/401/403 using **allowlisted tenant IDs or bounded-cardinality labels**, never raw bearer subjects/tokens in metric tags. Prevent one tenant from exhausting cluster-wide resources.

## 15. Adoption Checklist

1. Identified who issues, who holds, and who consumes the access token at each boundary.
2. Browser OAuth2 Login cookies are not blindly forwarded downstream.
3. TokenRelay forwards the right access token, never an ID Token/refresh token.
4. Gateway route targets are fixed/allowlisted, with outbound HTTPS/mTLS per policy.
5. Never trust `X-User`/`X-Tenant` from external clients; strip them or use verified signed assertions.
6. Downstream independently verifies JWT/introspection rather than relying solely on the Gateway.
7. Trusted issuer allowlist is managed server-side; JWKS is never fetched from an arbitrary `iss`.
8. Downstream checks `aud` intended for its own API, not just issuer/scope.
9. Route tenant matches the verified issuer/tenant claim/membership.
10. Scopes/roles are sufficient, with object ownership/row isolation in the database.
11. Service tokens are kept distinct from user tokens; use token exchange/OBO when delegation is required.
12. Access/refresh tokens, client secrets, and raw JWT claims are never leaked in logs.
13. Browser, machine API, and downstream errors return 302/401/403 per contract.
14. Tests cover cross-tenant access, spoofed headers, wrong audience, unknown issuer, expired tokens, missing scope, and gateway bypass.
15. Plans cover token expiry/revocation/logout, IdP/JWKS outages, and refresh rotation.
16. Multi-replica deployments have shared/secure state as needed and concurrency tests.
17. Never mix Servlet `HttpSecurity`/Gateway MVC APIs with `ServerHttpSecurity`/Gateway Server WebFlux.
18. Conduct a security review whenever adding a new tenant, route, issuer, or microservice.

## 16. Self-Check Questions

**Q1.** Once OAuth2 Login succeeds at the Gateway, does Orders still need to verify the access token?

**Answer:** Yes. Orders is a separate boundary and needs its own issuer/signature/exp/audience/scope/tenant and data ownership checks.

**Q2.** Does `TokenRelay=` automatically change `aud=gateway-api` to `aud=orders-api`?

**Answer:** No. The IdP must issue the right access token, or you must use token exchange/OBO per a supported protocol.

**Q3.** If a client sends `X-Tenant-Id: tenant-b`, can it access tenant B?

**Answer:** No. Headers/paths only indicate the requested tenant; access must match verified identity/membership and policy.

**Q4.** Does `TokenRelay=service-client` with client_credentials represent user Alice?

**Answer:** Not by default. It represents the service principal and requires dedicated delegation/actor semantics if acting for a user.

**Q5.** Why can the issuer in a JWT be read before verification while still not being trusted?

**Answer:** It is only used to **pick a manager from an allowlist**; that manager must verify signature/iss/exp/aud before granting authorities.

**Q6.** Can token A with a valid signature access the tenant B route?

**Answer:** Not under policy. The issuer allowed for tenant B, the tenant claim, and membership must match route B.

**Q7.** Why might a token with the right tenant and scope still be denied access to a specific order?

**Answer:** The order may belong to another user/team. Object-level authorization and tenant-scoped database queries are required.

**Q8.** What does `mockJwt()` prove?

**Answer:** It tests HTTP authorization with a mock Authentication; it does not prove JWT cryptographic verification or end-to-end token relay.

**Q9.** Does deleting the Gateway session automatically revoke all JWTs at Orders?

**Answer:** No. Local JWTs can remain valid until exp; a separate revocation policy is needed if required.

**Q10.** When downstream returns 403 for a missing scope, should the token be refreshed endlessly?

**Answer:** No. Refreshing does not grant extra permissions and can cause a retry storm. Classify the error and fix the scope/authorization contract.

## 17. Official References

- [Spring Cloud Gateway WebFlux — TokenRelay GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html)
- [Spring Cloud Gateway WebFlux — Spring Security Integration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/spring-security.html)
- [Spring Cloud Gateway — Server WebFlux Starter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/starter.html)
- [Spring Cloud — Spring Boot Release Train Compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Security — Reactive OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [Javadoc — JwtIssuerReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [Javadoc — JwtReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html)
- [Javadoc — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [Javadoc — ServerOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Spring Boot 4 Migration — OAuth2 Security Starter Names](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8693 — OAuth2 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
