# Boundaries Between Spring Security Servlet, WebFlux, Authorization Server, and Identity Management Systems

In a Java web application, many components are collectively referred to as "security": Spring Security, OAuth 2.0, OpenID Connect (OIDC), identity providers (IdP), authorization servers, and user management systems. They solve different problems. Understanding the boundaries helps you choose the right configuration, decide where to check permissions, and avoid designing an application that shoulders the responsibilities of an entire identity system.

**Lesson scope:** the perspective of a **Spring MVC application running on the Servlet stack**. This lesson compares architectural boundaries with Spring WebFlux, OAuth 2.0 Authorization Server, and Identity Management; it does not implement a full authorization server or IAM system.

## 1. What Is Spring Security Servlet Actually Responsible For?

Spring Security integrates into the application's **Servlet filter chain**. With Spring MVC, an HTTP request passes through security Servlet filters before reaching `DispatcherServlet` and controllers.

- **Authentication:** identifying the caller or verifying client-sent proof, such as an existing session, username/password, or a bearer access token.
- **Authorization:** deciding whether a request or method invocation may execute, based on principal, authorities, path, and business rules.
- **HTTP interaction protection:** managing/utilizing security context, sessions where applicable, CSRF, CORS integration, security headers, security error handling, and configured login/logout flows.
- **External system integration:** redirecting to an IdP for OIDC login, or validating access tokens issued by an Authorization Server.

Spring Security does **not automatically** become a repository for all user accounts, an HR provisioning system, an OAuth server issuing tokens, or the sole arbiter of all business permissions. An application can use another service for authentication while still having to control actions on its own data.

```text
HTTP request
   |
Servlet container (Tomcat/Jetty/...)
   |
Servlet FilterChain
   +-- Spring Security: DelegatingFilterProxy
   |      -> FilterChainProxy -> matching SecurityFilterChain
   |      -> authentication / load SecurityContext / authorization / error handling
   |
DispatcherServlet -> Controller -> Service -> business data
```

Key names in the Servlet stack are `HttpServletRequest`, `HttpServletResponse`, `HttpSecurity`, `SecurityFilterChain`, `Authentication`, and `SecurityContextHolder`. Under the common default strategy, `SecurityContextHolder` binds context to the current thread; do not assume context automatically follows every thread or asynchronous task. Persisting context across requests depends on mechanisms such as HTTP sessions or bearer tokens, not a fixed property of every Spring Security application.

**Right enforcement point:** Spring Security checks permissions at the HTTP boundary and can add checks at service/method level; constraints such as "only allow editing orders belonging to the current tenant" still must be enforced in the business or data-access layer.

## 2. Boundary Between Servlet and WebFlux

Spring MVC/Servlet and Spring WebFlux are **two different web processing models**. Both can use Spring Security, but they do not share the exact same filter sets, configuration APIs, or security context propagation mechanisms.

| Aspect | Spring MVC + Servlet | Spring WebFlux |
|---|---|---|
| Web foundation | Servlet API, request/response | Reactive HTTP, `ServerWebExchange` |
| Security chain | Servlet `Filter`, `FilterChainProxy` | Reactive `WebFilter`, `WebFilterChainProxy` |
| HTTP configuration | `HttpSecurity` → `SecurityFilterChain` | `ServerHttpSecurity` → `SecurityWebFilterChain` |
| Context | `SecurityContextHolder`, typically thread-based; context propagation integration when needed | Reactor `Context` / `ReactiveSecurityContextHolder` |
| Programming model | MVC controllers, servlet handling | `Mono`/`Flux`, reactive chains |
| Session | `HttpSession` when session-based | `WebSession` when session-based |

Do not copy code using `HttpSecurity`, `HttpServletRequest`, and `OncePerRequestFilter` into WebFlux expecting it to protect reactive routes; the reverse is also true. When integrating business logic using `WebClient` inside an MVC application, the application **remains a Servlet application**. Merely having Reactor/WebClient libraries on the classpath does not turn the filter chain into WebFlux.

With Spring Boot, when both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, standard web auto-configuration **prioritizes Spring MVC**. Always inspect the application type and starter set rather than guessing from imported class names. Running a reactive web server intentionally is a separate architectural decision.

**Shared principles:** both can protect routes, validate bearer tokens, act as an OAuth2 client or resource server, and enforce method security. The differences lie in request context, configuration APIs, and context propagation mechanisms.

## 3. Boundary Between Application, OAuth2 Authorization Server, and Resource Server

OAuth 2.0 separates roles. A real-world product may assume multiple roles, but their responsibilities must not be conflated:

| Role | Responsibility | Example in a System |
|---|---|---|
| **OAuth2 Client** | Requests authorization and obtains tokens via an appropriate flow; uses tokens to call resources | Web application/backend or mobile app |
| **Authorization Server (AS)** | Authenticates/authorizes per policy, issues access tokens, optionally issues refresh tokens, provides metadata/JWK/introspection depending on implementation | Central token-issuing service |
| **Resource Server (RS)** | Receives requests with access tokens, validates tokens, and enforces resource access permissions | Spring MVC REST API |
| **Resource Owner** | Entity capable of granting resource access in the corresponding flow | Usually the end user |

**Spring Security Servlet is an application-side integration library**: it can act as an OAuth2 Client (`oauth2Login`/`oauth2Client`), or configure the application as a Resource Server (`oauth2ResourceServer`). Enabling Resource Server does **not** create a `/token` issuing endpoint, `/authorize` authorization code endpoint, or client management. If you need to run your own Authorization Server, that is a separately designed and configured component/product.

### Flow A: MVC Application Logging In via OpenID Connect

```text
[Browser] -- opens page --> [MVC App: OIDC Client]
    |                              |
    | <- redirects to IdP/AS ------|
    | -- authenticates and consents (if needed) --> [IdP / Authorization Server]
    | <- redirects with code ------|
    |                              |-- exchanges code for token --> [AS]
    |                              |-- verifies ID token/user info per OIDC
    |                              |-- establishes app authentication/session
    | -- request + app cookie ----> [MVC + Spring Security]
```

OIDC builds on OAuth 2.0 to provide identity authentication information. The `ID token` is meant for the **client/relying party** to confirm the login event and identity per OIDC; do not use an ID token as an access token to protect APIs. A user logging in once with an IdP also does not mean all applications share a single `HttpSession`: each application typically manages its own session.

### Flow B: Client Calling a REST API with an Access Token

```text
[Client] -- requests token via appropriate flow --> [Authorization Server]
[Client] <-- access token ------------------------ [Authorization Server]
[Client] -- Authorization: Bearer ... -----------> [Servlet Resource Server]
[Servlet Resource Server] -- validates token + permissions --> [REST API]
```

For JWTs, the Resource Server must validate the signature against trusted keys, issuer, expiration, and other applicable conditions; **audience must be validated against the expected resource/API** if that is a system constraint—do not assume every configuration checks `aud` automatically. For opaque tokens, the Resource Server typically uses the Authorization Server's introspection endpoint. After the token is valid, the application still checks scopes/authorities and business permissions. Never trust client-supplied claims unless the token and a trusted issuer have been verified.

**Three token types are not interchangeable:**

- **Access token:** presented to a Resource Server; carries scopes/audience/lifetime suitable for the API.
- **ID token (OIDC):** provides authentication event and claims to an OIDC Client; do not use it to call APIs like an access token.
- **Refresh token:** held securely by an eligible client to request new access tokens; never present it directly to a Resource Server as a bearer access token.

## 4. Boundary with Identity Provider and Identity Management

Three closely related terms that do not completely overlap:

- **Identity Provider (IdP):** authenticates users, provides centralized login sessions, and supports protocols such as OIDC or SAML; an IdP often also acts as an OAuth2 Authorization Server, though conceptually the two roles differ.
- **Identity Management / IAM:** manages account lifecycles, organizations, groups, password/MFA policies, account provisioning/deprovisioning, HR/directory connections, or provisioning sync (for example, SCIM). Some administrative features may reside inside the same IdP product.
- **Application's Spring Security:** consumes authentication results, maps authorities, maintains security context within the application, and decides access to endpoints/methods/data.

Example: the HR system creates an employee; IAM provisions the account and groups; the IdP authenticates MFA; the AS issues an access token; the Servlet API validates the token and `SCOPE_orders.read`; the service returns only orders belonging to the allowed tenant and user. No single component in that chain automatically replaces all the other steps.

**Boundaries easily overlooked:**

1. **Centralized login ≠ centralized business authorization.** A "sales" group from the IdP can help map an authority, but order ownership or approval status must be verified inside the application.
2. **Account lockout ≠ already-issued JWTs immediately invalidated.** Self-verifying JWTs can remain valid until expiration unless the architecture adds revocation/checks; consider short TTLs, introspection, or revocation policies when business requirements demand it.
3. **App logout ≠ full SSO logout.** Clearing a local session/cookie does not necessarily end the IdP session or revoke all access tokens. Supporting single logout/back-channel logout requires designing the protocol and operations accordingly.
4. **User/group sync ≠ instant permission sync.** Claims in a token are a snapshot at issuance time; permissions can change afterward. Design token lifetimes, mapping updates, and sensitive permission checks appropriately.
5. **An organization with multiple issuers/tenants.** Do not accept a token merely because its signature is valid; bind issuer, audience, token type, and tenant per trust configuration, especially in multi-tenant APIs.

## 5. Configuration Example: Servlet Resource Server Protecting an API

Suppose a **Spring Boot MVC application serves only REST APIs**. Clients obtain OAuth2 access tokens from an external Authorization Server. This application does not issue tokens, implement a login page, or operate its own identity store.

Typical dependencies: `spring-boot-starter-web` and `spring-boot-starter-oauth2-resource-server`. With Java 17+ and compatible Spring Boot/Spring Security versions, create `src/main/java/example/security/ServletApiSecurityConfig.java`:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ServletApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers("/api/**").hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

Example issuer configuration in `application.yml` (the URL is only a sample address; replace it with the real trusted issuer):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/issuer
```

Meaning:

- `oauth2ResourceServer(...jwt(...))` validates JWT access tokens per issuer/JWK configuration; it does **not issue** JWTs.
- `hasAuthority("SCOPE_orders.read")` illustrates the default mapping from scope `orders.read` to a `SCOPE_`-prefixed authority. Business permissions like resource ownership must be checked additionally.
- `STATELESS` does not store the security context across subsequent requests in an HTTP session for this mechanism; each request carries the required token.
- `csrf(...disable)` **only fits the assumptions of this example**: the API does not rely on browser-auto-sent cookies/sessions for authentication, using bearer tokens actively placed in `Authorization` by the client instead. If the API also uses cookies/sessions or auto-sent credentials, evaluate and configure CSRF appropriately instead of copying this disable call.
- `denyAll()` blocks paths outside the illustrated API; adjust routing to match system requirements and avoid accidentally exposing endpoints.

This is a **configuration class used inside a Spring Boot project**, not a standalone Java program run solely with `javac`. Running it requires a project, dependencies, an active issuer configuration, and appropriate controllers. The example produces no fixed stdout: observed outcomes are HTTP `200`/`401`/`403` depending on the controller, token, and permissions.

**Be careful with HTTP status:** requests without valid proof of authentication usually receive `401 Unauthorized`; authenticated requests lacking permissions usually receive `403 Forbidden`. For public endpoints, the controller still determines the status code; not every valid request returns `200`.

## 6. Same Goal on WebFlux: Different Configuration

The following snippet is **only a comparison example in a separate WebFlux application**—do not add it to the Servlet project in section 5. With `spring-boot-starter-webflux` and the corresponding Resource Server starter, use `ServerHttpSecurity` and `SecurityWebFilterChain`:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveApiSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/**").hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }
}
```

The CSRF and audience rules from section 5 **still apply**. Do not copy this style of code into a Servlet security filter chain. Reactive services store and propagate authentication via the Reactor context; avoid coding as if every step executes on one fixed thread.

## 7. Choosing the Right Role for the Scenario

| Real-World Need | Primary Component | Work Still Belonging to Spring Security Servlet |
|---|---|---|
| MVC website letting users log in via SSO | OIDC IdP/AS + app acting as OIDC Client | Login callback, security context, session, CSRF, route/method authorization |
| REST API receiving `Authorization: Bearer ...` | AS issuing tokens + app acting as Resource Server | Token validation, scope/authority checks, data-level permissions |
| Building your own access/refresh token issuing service | Dedicated Authorization Server | If the AS runs on Servlet, its endpoints still need protection; cannot be solved by Resource Server config alone |
| Managing HR lifecycle, MFA, user lifecycle, groups | IAM/IdP/directory/SCIM | Identity integration and mapping trusted claims to app permissions |
| Fully reactive HTTP processing | Spring WebFlux + reactive Spring Security | Use `SecurityWebFilterChain`, `ServerHttpSecurity`, Reactor context |
| MVC app only needing to call a reactive API via `WebClient` | Spring MVC/Servlet, WebClient is an HTTP client | Keep `SecurityFilterChain`; handle tokens when calling downstream per OAuth2 client responsibilities |

An application can also act as both an **OIDC Client** (user login) and an **OAuth2 Client** (calling downstream APIs), or simultaneously expose APIs as a **Resource Server**. This is a combination of roles within one application, not an erasure of protocol and responsibility boundaries.

## 8. Common Misconceptions and How to Check

**Misconception 1 — "Using OAuth2 means the app automatically has a token-issuing server."**  
Incorrect. `oauth2Login` and `oauth2ResourceServer` are Spring Security's client/resource server capabilities. Check which actual system owns the authorization endpoint, token endpoint, signing keys, and issuance policies.

**Misconception 2 — "WebFlux and MVC only differ by a `Mono` return type."**  
Incorrect. Both the HTTP runtime and security filter chain differ. Check starters, web application type, and configuration beans. On Servlet, look for `SecurityFilterChain`; on WebFlux, look for `SecurityWebFilterChain`.

**Misconception 3 — "A valid JWT means the user can perform any operation."**  
Incorrect. You must validate issuer/audience for the right resource, expiration, scopes/authorities, and permissions on the specific object. Having an order-reading scope does not automatically grant access to another tenant's orders.

**Misconception 4 — "An ID token can be sent to any API instead of an access token."**  
Incorrect. ID tokens serve the OIDC Client; APIs receive access tokens targeted at the respective resource. Separate validation and audience checks by role.

**Misconception 5 — "With SSO enabled, the website no longer needs session/CSRF protection."**  
Incorrect. Web MVC still has cookies/sessions and state-changing requests. SSO is the source of identity authentication, not a replacement for the application's HTTP protection mechanisms.

**Misconception 6 — "Permissions from IAM are always immediately up to date."**  
Not necessarily. Tokens have TTLs, caches, mappings, and provisioning delays. Define access revocation SLAs and where sensitive permission checks occur.

**Misconception 7 — "An API returning 302 to a login page means bearer authentication is working."**  
For a pure JSON/bearer API, redirecting to form login usually indicates the wrong entry point or misaligned filter chains. Determine whether the API uses bearer tokens or browser sessions; configure the unauthenticated response for the right client type.

## 9. Process for Defining Boundaries Before Implementation

1. **Identify the HTTP stack:** Servlet/Spring MVC or WebFlux, and whether `WebClient` is combined; choose the matching security chain and starters.
2. **Identify who authenticates users:** internal accounts, OIDC/SAML IdP, or pre-issued tokens; map out the browser redirect or bearer flow.
3. **Identify who issues tokens:** which Authorization Server, issuer, JWK, audience, scopes, expiry, and revocation mechanism.
4. **Identify application roles:** OIDC/OAuth Client, Resource Server, or multiple roles; avoid accidentally mixing ID tokens and access tokens.
5. **Identify where authorization decisions are made:** endpoint/method policies in Spring Security, ownership/tenant/state checks in the service or data layer.
6. **Identify browser security state:** cookies/sessions, CSRF, CORS, local logout, and SSO logout; never disable protections just to make requests work.
7. **Test negative boundaries:** missing token, wrong issuer, wrong audience, expired token, missing scope, wrong tenant, disabled user, and old tokens; verify expected HTTP status codes and revocation behavior per design.

### Self-Check

- A Servlet API receives a JWT from an IdP: **who issues the token, who validates it, and who decides whether the user can view order #42?** The AS issues it, the Resource Server validates it, and the application checks scopes and order permissions.
- An MVC project calls an API using `WebClient`: **must it switch to `ServerHttpSecurity`?** No; the HTTP server still uses the Servlet stack.
- A user logs out of an OIDC web app: **are all API bearer tokens and all SSO sessions destroyed?** Not guaranteed; depends on implemented session, token revocation, and cross-application logout mechanisms.
- A JWT has a valid signature, but `aud` belongs to a different API: **should it be accepted?** No; the Resource Server should bind tokens to the expected resource per validation policy.

**Remember:** Spring Security Servlet protects the **requests and operations of a Servlet application**; WebFlux has its own security runtime; the Authorization Server **issues/authorizes tokens**; and IdP/IAM **authenticates and manages identities**. They collaborate across clear protocols and trust boundaries, while final authorization on business data must still be enforced by the application that owns the data.