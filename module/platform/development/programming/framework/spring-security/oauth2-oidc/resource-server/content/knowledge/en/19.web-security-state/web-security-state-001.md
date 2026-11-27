# Per-Request Bearer Authentication and Session Management Choices

In **Spring Security OAuth 2.0 Resource Server**, a Bearer access token is the credential that a client sends to an API to prove access rights. Unlike traditional web applications that log in once and store `Authentication` in an `HttpSession`, an API using Bearer tokens can **authenticate each request** without needing a server-side login session.

However, the statement "a Resource Server is stateless" is often interpreted too broadly. An API that does not use `HttpSession` to remember callers still has **JWK caches, introspection, databases, rate limits, transactions, and network connections**. An application can also serve both a **stateless Bearer REST API** and a **session-based browser interface**; each area needs an appropriate protection policy.

This lesson explains the relationship between per-request Bearer authentication, `SecurityContext`, `HttpSession`, `SessionCreationPolicy`, and choices for mobile, SPA, service-to-service, browser login, and BFF architectures. Examples use **Spring Boot 3 / Spring Security 6, Servlet stack**. Default behavior may vary by filter chain, repository, and version; always verify the actual HTTP paths of your application.

## 1. What is per-request Bearer authentication?

A client calls the API:

```http
GET /api/orders/101 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

The next request **must still carry the credential**:

```http
GET /api/orders/102 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

In the stateless Resource Server model:

1. Spring Security reads the Bearer token from the request.
2. The authentication provider calls `JwtDecoder` or `OpaqueTokenIntrospector`.
3. When the token is accepted, the framework creates an `Authentication` with principal and authorities.
4. `Authentication` is placed in the `SecurityContext` for the **request currently being processed**.
5. The framework finishes and clears the context according to the request lifecycle.
6. The next request must present a token; the API **does not rely on a login session saved from a previous request**.

**Stateless here means not depending on a login session across requests**, not that the application is completely devoid of state.

With JWTs, a Resource Server typically verifies signatures and claims using trusted public keys. With opaque tokens, the application typically calls introspection on the Authorization Server. Both can operate without needing `HttpSession` to store the principal.

## 2. Authentication flow of two independent requests

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant P as AuthenticationProvider
    participant S as SecurityContext
    participant A as Orders API
    C->>F: Request 1 + Bearer token
    F->>P: authenticate(token)
    P-->>F: Valid Authentication
    F->>S: Attach Authentication for request 1
    S->>A: Principal and authorities
    A-->>C: HTTP response 1
    Note over S: Clear context when request completes
    C->>F: Request 2 + Bearer token
    F->>P: Fresh authenticate(token)
    P-->>F: Valid Authentication
    F->>S: Attach Authentication for request 2
    S->>A: Principal and authorities
    A-->>C: HTTP response 2
```

**Authenticating each request does not mean downloading JWKS over the network on every request.** `JwtDecoder` can use a cached JWK Set, while a custom `OpaqueTokenIntrospector` can cache introspection results according to policy. These caches **are not web login sessions**.

If request 2 does not carry a Bearer token, an endpoint requiring authentication must reject it, even if request 1 just succeeded. This is an invariant that must be tested.

## 3. Distinguishing Bearer token, `SecurityContext`, `HttpSession`, and caches

| Component | Where it exists | Role | Is it a login session? |
| --- | --- | --- | --- |
| **Bearer access token** | Held by client, sent per request. | Credential for the API call. | No. |
| **`SecurityContext`** | Scoped to request processing/thread/configured repository. | Holds the current `Authentication`. | Can be saved to a session when policy permits. |
| **`HttpSession`** | Server or distributed session store; browser holds ID. | Maintains state across requests. | Can be. |
| **Session cookie** (`JSESSIONID`) | Automatically sent by browser per cookie policy. | References a server-side session. | Commonly used for web login. |
| **JWK/introspection cache** | Pod memory, Redis, or another cache layer. | Reduces cost of fetching keys/checking tokens. | No. |
| **Database, rate limit, connection pool** | Application infrastructure. | Business data and resource management. | Not a login session by itself. |

A stateless Bearer API **still creates a `SecurityContext` during the request** so controllers/services can read the identity; the difference is that it does not restore authentication from a session between requests.

In the Servlet stack, `SecurityContextHolder` defaults to a `ThreadLocal`-based strategy; asynchronous processing styles require their own propagation policy and do not automatically inherit identity across every thread.

## 4. `SecurityContext` and `HttpSession` are not identical

After successful JWT authentication:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
```

In a JWT Resource Server, `auth` is typically a `JwtAuthenticationToken`; with opaque tokens, it is typically a `BearerTokenAuthentication`.

`HttpSession` is a different mechanism:

```java
HttpSession existing = request.getSession(false);
```

`getSession(false)` only retrieves an already-existing session. Whereas:

```java
HttpSession createdOrExisting = request.getSession();
```

can create a session. `SessionCreationPolicy.STATELESS` controls how **Spring Security** creates/uses sessions for authentication; **it does not prevent other servlets/controllers/libraries from calling `getSession()`**.

Therefore, when saying "the API does not use sessions", what matters is **whether Spring Security relies on a session to retrieve/store Authentication for subsequent requests**, not merely whether some cookie appears in the system.

## 5. Four `SessionCreationPolicy` options

Spring Security has the enum:

```java
org.springframework.security.config.http.SessionCreationPolicy
```

| Policy | Main Spring Security behavior | Suitable use cases |
| --- | --- | --- |
| `ALWAYS` | Spring Security always creates an HTTP session. | Specific session needs; rarely used for pure Bearer APIs. |
| `IF_REQUIRED` | Creates a session when actually needed. | Web login, saved requests, storing authentication. |
| `NEVER` | Spring Security does not create a session itself, **but may use an existing one**. | Want to restrict new creation while still accepting an existing session. |
| `STATELESS` | Spring Security does not create and **does not use a session to obtain `SecurityContext`**. | Bearer APIs authenticating each request independently. |

Specifically:

```text
NEVER != STATELESS
```

With `NEVER`, a session created by another component may still be used by security logic depending on configuration. With `STATELESS`, the API does not rely on a stored session to restore the principal.

`IF_REQUIRED` does not necessarily create a session for every request: it also depends on login type, request cache, and active security features. Similarly, `STATELESS` does not guarantee that **the entire application or proxy** will never issue a session cookie.

## 6. Stateless JWT Resource Server with Spring Boot

Gradle:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

YAML:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
```

A dedicated chain for the API:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Here:

- `securityMatcher("/api/**")` limits **the scope of the chain**.
- `STATELESS` prevents Spring Security from using a session to restore authentication.
- `oauth2ResourceServer().jwt()` accepts Bearer JWTs and authenticates each request.
- `hasAuthority("SCOPE_orders.read")` checks functional permissions mapped from the token.
- `anyRequest().denyAll()` applies **within this chain** and does not protect URLs outside `/api/**`.
- `csrf.disable()` is only appropriate under the assumption that **the API accepts Bearer tokens via header and does not use auto-sent cookies/browser credentials for authentication**.

Applications with Actuator, Swagger, browser login, webhooks, or other routes need separate security chains/fallbacks and policies.

## 7. A subsequent request without Bearer does not become authenticated

A valid request:

```bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/orders/101
```

The next request:

```bash
curl -i https://api.example.com/api/orders/101
```

must be rejected if the endpoint requires a JWT, even from the same IP address right after a successful request. The server does not "remember the caller by IP" or automatically restore `Authentication` from a previous request.

A token can be **validly reused while still within its validity period**; statelessness does not turn a token into a one-time credential and does not by itself solve Bearer token replay if a token is stolen.

## 8. `JwtDecoder` verifies every request without necessarily making network calls

A JWT Resource Server uses a decoder to verify signatures, issuer, time claims, and validators per API policy. Public keys may already reside in the pod's JWK cache.

```text
Every request needs authentication
     !=
Every request needs to call the Authorization Server
```

JWT token:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1900000000
}
```

This payload is illustrative only; it is not a signed token. The API must check `aud` according to its contract, rather than assuming every decoder configured with an issuer already validates the audience.

Different pods may cache JWKS at different times when the issuer rotates keys. This is **key cache lifecycle**, not a login session. Configuring `STATELESS` does not make pods automatically share a JWK Set or perform automatic revocation.

## 9. Opaque tokens can also authenticate statelessly

Spring Boot opaque token:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

DSL:

```java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults()))
```

With opaque tokens, the Resource Server typically calls the introspection endpoint to learn token status and obtain the principal; a custom introspector can cache results according to a TTL/policy.

| Factor | Bearer JWT | Bearer opaque |
| --- | --- | --- |
| Common verification mechanism | Signature and claims via `JwtDecoder`. | `OpaqueTokenIntrospector` calling upstream. |
| Spring Security principal | Usually `JwtAuthenticationToken`. | Usually `BearerTokenAuthentication`. |
| Requires login session? | No. | No. |
| Can use `STATELESS`? | Yes. | Yes. |
| Network dependency on auth | Fetch/refresh JWK Set depending on cache state. | Usually introspection, unless cached/policy-driven. |
| Token revocation | Depends on expiry, denylist, or online policy. | Depends on upstream state and cache. |

**Opaque does not mean stateful.** It simply indicates that the token is not self-verified by the Resource Server from JWT contents in the usual way.

## 10. When should sessions be used?

| Architecture | Credential | Session at Resource Server? | Notes |
| --- | --- | --- | --- |
| Mobile app → REST API | Bearer in header. | Usually no. | Token storage, lifetime/refresh. |
| Backend-to-backend | Client Credentials access token. | Usually no. | Service identity, audience, scope. |
| CLI or integration worker | Bearer token. | Usually no. | Handling 401, refresh via OAuth Client. |
| SPA calling API directly | Bearer header added by JS. | API usually no. | XSS, CORS, token storage. |
| Server-rendered web | Session cookie. | May be needed. | CSRF, session fixation, logout, timeout. |
| BFF/OIDC login | Browser cookie, server holds downstream tokens. | Web/BFF usually yes. | CSRF, cookies, server-side token lifecycle. |
| Combined API and web app | Bearer for API; cookie for web. | Separated by chain. | Do not let web sessions replace Bearer. |

Choose the policy based on **how the client sends credentials**, the need to persist login, and endpoint boundaries. No single enum value is right for all applications.

## 11. `STATELESS` does not guarantee the entire server never sets cookies

A common misconception:

> With `STATELESS`, the application is guaranteed never to return `Set-Cookie: JSESSIONID`.

This is false because `STATELESS` applies to **Spring Security session usage**. A servlet/controller, another filter, a web framework, or a reverse proxy can still create its own session/cookie.

For example, in a controller:

```java
@GetMapping("/api/debug")
public String debug(HttpServletRequest request) {
    request.getSession(); // May create an HttpSession
    return "ok";
}
```

If a cookie appears, determine **which component created it**. Merely seeing `JSESSIONID` does not prove Security restored the principal from a session.

More important evidence for a Bearer-only API:

```text
Request 1: with Bearer -> authenticated
Request 2: without Bearer, cookie only -> must still be rejected
```

## 12. `SecurityContextRepository` and saving context

Spring Security uses the `SecurityContextRepository` abstraction to load/save the security context per configuration. Some implementations:

| Repository | Role |
| --- | --- |
| `HttpSessionSecurityContextRepository` | Can save/restore context from HTTP session per policy. |
| `RequestAttributeSecurityContextRepository` | Keeps context within the **same request** via request attributes/appropriate dispatches. |
| `NullSecurityContextRepository` | Does not persist context via a repository. |
| `DelegatingSecurityContextRepository` | Combines multiple loading/saving strategies in order. |

Spring Security 6 introduced changes to context-loading filters and explicit save policies. **Do not assume every `STATELESS` chain uses the exact same repository class across all versions/configurations.** What must be ensured is that the Bearer API's principal comes from authenticating this request's credential, not from an old `HttpSession`.

The presence of a context in request attributes **does not make an API session-based**, because request attributes are not used to remember a user across two independent requests.

## 13. Do not disable filters wholesale just to be stateless

Example of an extreme configuration:

```java
http
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .securityContext(context -> context.disable())
    .anonymous(anonymous -> anonymous.disable())
    .requestCache(cache -> cache.disable());
```

This is not default guidance for building a good API. `STATELESS` relates to sessions, whereas SecurityContext, anonymous authentication, exception handling, and request cache have separate responsibilities. Disabling them indiscriminately can make the filter chain unpredictable or alter authorization behavior.

For a pure Bearer API, it is usually best to start with `STATELESS`, `oauth2ResourceServer`, scoped authorization, CSRF/CORS matching the threat model, and a clear fallback chain. Only customize other repositories/filters when there is a verified need.

## 14. `401` and `403` when the API has no session

| Request | Authentication | Authorization | Typical result |
| --- | --- | --- | --- |
| No Bearer on protected API | Missing principal. | Cannot authorize. | `401`. |
| JWT with invalid signature/issuer/expiry/audience | Authentication failed. | Token claims not used. | `401`. |
| Valid JWT, missing `orders.read` | Has principal. | Missing authority. | `403`. |
| JWT with right scope but wrong tenant/owner | Succeeded. | Domain policy denies. | `403` or `404`. |
| Valid JWT and valid object | Succeeded. | Permitted. | `2xx` if business logic succeeds. |
| Only web session cookie | STATELESS Bearer-only API does not use session to restore principal. | Protected API denies. | Usually `401`. |

Spring Security OAuth 2.0 Bearer typically returns a `WWW-Authenticate: Bearer` header; invalid token errors may include `invalid_token`. The actual status code depends on the entry point, access denied handler, chain, and exception mapping.

For REST APIs, **do not default to redirecting to an HTML login page** instead of sending an appropriate 401 to the client. A web login session, on the other hand, may intentionally redirect to `/login`.

## 15. CSRF must be evaluated by how the browser sends credentials

CSRF (*Cross-Site Request Forgery*) exploits the fact that browsers **automatically attach credentials** such as session cookies to requests sent to a server from another website.

For an API accepting `Authorization: Bearer` explicitly added by trusted code, an arbitrary website cannot make the browser send the right Bearer token via a plain HTML form without knowing the token. Therefore, a Bearer API that **uses only the Authorization header and does not use cookies for authentication** typically does not need traditional CSRF protection.

However, an application with:

```http
Cookie: access_token=<token>
```

or `JSESSIONID` still has credentials automatically sent by the browser; CSRF must be considered, even if Spring Security uses `STATELESS` for part of the application.

| How credential is sent | Automatically attached? | Conclusion |
| --- | --- | --- |
| Bearer header added by client | Not in the auto-sent cookie way. | Traditional CSRF usually applies less, though XSS/token theft still exist. |
| Session cookie | Yes. | Needs CSRF protection for state-changing requests. |
| JWT in `HttpOnly` cookie | Possible per cookie policy. | `HttpOnly` **does not solve CSRF**. |
| BFF session cookie | Yes. | Needs CSRF protection and cookie attributes. |
| Browser-cached HTTP Basic Auth | Can be auto-attached. | Needs CSRF evaluation. |

**Stateless does not automatically mean CSRF-proof.** If an API uses cookies as credentials, do not copy `.csrf(csrf -> csrf.disable())` just because the token is formatted as a JWT.

## 16. `HttpOnly`, `Secure`, `SameSite` cookies and web sessions

When a browser uses a session cookie:

- `HttpOnly` helps restrict JavaScript from reading the cookie, reducing one avenue of session exposure via XSS.
- `Secure` requires the cookie to be sent only over HTTPS.
- `SameSite=Lax` or `Strict` mitigates cross-site scenarios depending on product needs.
- `Domain` and `Path` should be restricted to the proper scope.
- Login should include session fixation protection/session ID rotation.
- Sessions must have timeout, logout, and invalidation policies.

These measures complement one another and **do not replace CSRF tokens and origin checks when needed**. SameSite is not a guarantee that every CSRF variant is blocked.

In Spring Boot, many cookie attributes live under `server.servlet.session.cookie.*`; verify support/version and behavior behind reverse proxies/TLS termination.

## 17. SPA calling the Resource Server directly

An SPA can:

```text
Browser SPA
  -> Authorization Code + PKCE with IdP
  -> receives access token according to client architecture
  -> explicitly adds Authorization: Bearer to API requests
  -> Resource Server authenticates each request
```

Deciding where to store tokens is also critical:

| Token storage | Benefits | Risks |
| --- | --- | --- |
| JavaScript memory | Does not persist long across reloads. | Runtime XSS can still use/steal the token. |
| Local/session storage | Convenient across reloads/tabs. | Same-origin JavaScript, including XSS, can read it. |
| `HttpOnly` cookie | JavaScript cannot read the token directly. | Browser auto-sends cookie: requires CSRF, cookie policy. |
| BFF holds token server-side | Limits token exposure to browser JS. | Needs session store, CSRF, server-side refresh/rotation. |

A `STATELESS` API does not dictate where the client must keep tokens. It only defines how the Resource Server uses sessions to identify requests.

## 18. A BFF has a session while the downstream Resource Server stays stateless

The **Backend for Frontend** pattern:

```mermaid
flowchart LR
    B["Browser"] -->|"Session cookie"| F["BFF / Web backend"]
    F -->|"Bearer access token"| A["Orders Resource Server"]
    F <-->|"OIDC/OAuth login and refresh"| I["Authorization Server"]
```

Separate the two relationships:

1. **Browser ↔ BFF**: web session, cookies, CSRF, login/logout, and server-side token storage.
2. **BFF ↔ Resource Server**: each downstream request carries an access token intended for the API, with the right issuer/audience/scope.

There is no contradiction here. `SessionCreationPolicy.IF_REQUIRED` can fit the BFF, while the downstream Resource Server uses `STATELESS`.

The BFF must not turn a browser session cookie into unconditional access on the API: it must select the proper access token and never bypass the Resource Server's domain authorization.

## 19. `oauth2Login()` differs from `oauth2ResourceServer()`

| Configuration | Role | Authentication object |
| --- | --- | --- |
| `.oauth2ResourceServer(o -> o.jwt(...))` | API verifies Bearer JWT access tokens. | Usually `JwtAuthenticationToken`. |
| `.oauth2ResourceServer(o -> o.opaqueToken(...))` | API introspects opaque access tokens. | Usually `BearerTokenAuthentication`. |
| `.oauth2Login(...)` | OAuth 2.0/OIDC Client login via authorization code. | Web Authentication that can be stored in a session. |
| `.formLogin(...)` | Form-based web login. | Authentication retained per web session policy. |

An OIDC **ID Token** serves the OIDC Client to identify the End-User; it is not by itself an access token meant for a Resource Server. A BFF using `oauth2Login()` needs `spring-boot-starter-oauth2-client`, client registration/provider config, sessions, and OIDC logout flow.

A Resource Server can use `spring-boot-starter-oauth2-resource-server` alone without a login page or web session.

## 20. Combining web sessions and Bearer APIs with two `SecurityFilterChain`s

Example of a Spring Boot application having both `/api/**` and a website using form login:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DualSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/assets/**", "/error"
                ).permitAll()
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

In this example:

- Chain **1** matches `/api/**`, requires a Bearer JWT, and does not use a session to restore authentication.
- Chain **2** is the **fallback** for remaining URLs; it uses web login and can create a session when needed.
- CSRF on the web chain **remains enabled** because nothing disables it.
- `/login` is handled by the web chain; the application needs to configure an appropriate user authentication source for form login.
- When using an OIDC Client, `.formLogin(...)` can be replaced with `.oauth2Login(...)` along with OAuth Client dependencies/configuration.

**Do not apply this snippet blindly** to systems whose API also accepts cookies, BFF routes, Actuator on another port, or flows with different CSRF needs. You must determine which credentials are allowed on each endpoint group.

## 21. The first matching chain is selected

Spring Security `FilterChainProxy` picks **the first chain that matches the request**, rather than running all chains sequentially. With the configuration above:

```text
GET /api/orders/101 -> @Order(1) chain
GET /account        -> @Order(2) chain
GET /login          -> @Order(2) chain
```

An `anyRequest().denyAll()` inside the `/api/**` chain **does not protect** `/admin`, `/actuator`, or `/swagger-ui` outside the matcher. If you only create a single chain bean for `/api/**`, Spring Boot may back off its default web security auto-configuration, leaving other URLs without a protective chain.

Therefore, a **fallback chain or equivalent policy** is needed for paths outside the API. In tests, verify the right chain/entry point for both protected routes and non-existent routes.

## 22. A web cookie cannot substitute for an API Bearer access token

A user logged into the web has:

```http
Cookie: JSESSIONID=...
```

Calling the API:

```http
GET /api/orders/101
Cookie: JSESSIONID=...
```

against a `STATELESS` Bearer-only API chain **must not automatically succeed** just because the browser is logged in. This is a boundary that must be tested:

1. Log into the web successfully and obtain the session cookie.
2. Call protected `/api/orders/101` using **only the cookie**.
3. The API must reject the request for missing a Bearer token.
4. Send a valid Bearer JWT with the appropriate scope.
5. Authentication/endpoint policy permits it, after which tenant/owner checks still apply.

If the API permits step 3, check `securityMatcher`, session repository, reverse proxy identity headers, and any additional authentication logic.

## 23. Proxies/gateways can also create sessions outside Spring Security

Even when the API chain is stateless, check:

- Does the ingress forward web cookies to the API?
- Does a gateway use an SSO session and inject an `X-User` or `Authorization` header?
- Does a reverse proxy issue its own session cookie distinct from `JSESSIONID`?
- Does the API blindly trust an identity header that should only be set by the proxy?
- Are public web origins, BFF routes, and protected API origins clearly separated?

A cookie appearing on a request is not necessarily **used to authenticate** the request. However, if a gateway or adapter turns a cookie into a principal, that is another authentication mechanism requiring trust boundaries, stripping spoofed headers, and its own policy.

Do not treat `STATELESS` in Spring Security as proof that every layer in front of it is stateless.

## 24. Request cache/redirect fits web apps better than REST APIs

Web session login typically works as:

```text
GET /account
  -> not logged in
  -> save original request
  -> redirect /login
  -> login
  -> redirect /account
```

This flow suits browsers and can use `HttpSession`/`RequestCache`.

A Bearer API typically works as:

```text
GET /api/orders/101 without token
  -> 401 Unauthorized
  -> client handles obtaining token/login itself
```

There is no need to save API requests in a session for HTML redirects. If an application mixes web/login and Bearer APIs, `AuthenticationEntryPoint` and request cache must be chosen per chain type so mobile/server-side clients do not unexpectedly encounter `302 /login`.

## 25. CORS preflight may not carry a Bearer token

An SPA from `https://app.example.com` calling `https://api.example.com` can send a preflight:

```http
OPTIONS /api/orders/101 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Preflights typically **do not carry the main request's Bearer token**. If authentication runs before the CORS policy, the browser may report a CORS error instead of being able to call the API.

Example `CorsConfigurationSource`:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of(
        "https://app.example.com"
    ));
    config.setAllowedMethods(List.of(
        "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
    ));
    config.setAllowedHeaders(List.of(
        "Authorization", "Content-Type"
    ));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

In the security chain:

```java
.cors(Customizer.withDefaults())
```

CORS controls browsers by origin; **it does not replace authentication or authorization**. Curl and server-to-server clients can still make HTTP calls; every business request must use a valid Bearer token.

## 26. Access token expiry differs from session timeout

Suppose a product has:

```text
Web session timeout: 30 minutes of inactivity
Access token lifetime: 10 minutes
Refresh token lifetime: per Authorization Server policy
```

These three clocks **do not automatically stay in sync**:

- BFF web session is still alive, but the downstream access token expired: the BFF needs to refresh if authorized.
- Browser session expired, but a copied token is still valid: the Resource Server may continue accepting the token unless a linked revocation mechanism exists.
- A `STATELESS` Resource Server does not automatically extend the `exp` claim.
- The OAuth Client/Authorization Server manages refresh tokens per grant and policy; business APIs normally do not accept refresh tokens in place of access tokens.

**Do not use `JSESSIONID`'s lifetime as the JWT's expiration**, or treat a JWT as a session ID. They have different purposes, validation, and lifecycles.

## 27. Logging out of a session does not equate to revoking a Bearer token

**Web session:**

```text
Browser -> logout following CSRF policy
Server -> invalidate session and clear context
Browser -> session cookie is no longer a valid login
```

**Stateless Bearer:**

```text
Client deletes access token from storage
Resource Server has no login session to invalidate
A copy of the token captured earlier may remain valid
  until exp or a revocation/denylist mechanism takes effect
```

For near real-time revocation requirements, you may need opaque introspection, a denylist, token versions, short access token lifetimes, or online policies. Those measures are **token authorization/revocation design**, and do not appear automatically by setting `SessionCreationPolicy`.

`SecurityContextHolder.clearContext()` at the end of a request also **does not revoke tokens**.

## 28. Session fixation and Bearer replay are two distinct threats

| Model | Threat | Mitigation |
| --- | --- | --- |
| Web session | Session fixation. | Change/rotate session ID after login; session fixation protection. |
| Web session | Stolen cookie/session ID. | `Secure`, `HttpOnly`, SameSite, TLS, cookie scoping, timeout, and logout. |
| Bearer API | Exposed/replayed access token. | TLS, protected token storage, short lifetime, revocation when needed. |
| Bearer API | Wrong issuer/audience token. | JWT/opaque validation matching the protected resource contract. |
| Both | Valid caller accessing wrong tenant/owner. | Functional scope + domain-level authorization. |

Spring Security provides session fixation protection for web logins per version configuration. It **does not make a Bearer token a proof-of-possession token**. Sender-constrained token mechanisms like mTLS-bound access tokens or DPoP require dedicated supporting architecture.

## 29. Multiple pods: session store vs. JWK/introspection cache

```text
Load balancer
  -> API pod A
  -> API pod B
  -> API pod C
```

A stateless Bearer API does not need to look up an old `HttpSession` on pod A when the next request lands on pod B. Each pod authenticates credentials according to its own policy.

A session-based web app may need sticky sessions or a shared session store like Spring Session + Redis to restore login state across pods.

| Criterion | Stateless Bearer API | Stateful web session |
| --- | --- | --- |
| Session replication for auth | Usually no. | May be required. |
| Scaling replicas | No need to migrate login sessions across pods. | Must account for store, timeouts, sticky routing. |
| Logout | Does not automatically revoke access tokens. | Can invalidate session. |
| IdP outage | JWT with keys can operate locally; opaque depends on introspection. | Existing sessions may keep working depending on config. |
| Redis session store down | No direct impact if API does not use it for auth. | Can impact web sessions. |

`STATELESS` does not remove the need to consider JWKS refresh, introspection caches, DNS/TLS, clock skew, or tenant membership.

## 30. Stateless does not mean business permissions are always up to date

An unexpired JWT:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "alice",
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

may still be sent after Alice's `tenant-a` membership is revoked. The API authenticates the Bearer token on each request, **but does not automatically ask the database whether membership was revoked**.

```text
Bearer authentication on every request
   !=
Domain authorization always checked in real time
```

If early tenant access revocation is required, you need a policy checking current membership or an appropriate permission cache TTL/invalidation. JWT validation, OAuth scope, tenant membership, and owner checks are independent layers.

## 31. `@Async`, schedulers, and context propagation

In the Servlet stack, `SecurityContext` normally lives in the request-handling thread. A method:

```java
@Async
public void runExport() {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
}
```

must not assume `auth` will be the JWT principal from the original request. Spring Security provides `DelegatingSecurityContext...` mechanisms for propagation when needed, but passing full contexts/credentials into background work must account for lifecycle, privacy, and revocation.

An approach that can work well:

1. Authenticate and authorize **before enqueuing the job**.
2. Pass a minimal `CallerIdentity` or verified capability, avoiding raw Bearer tokens when unnecessary.
3. When the job runs, check domain policies against current state if needed.
4. Distinguish the job requester from the executing **service identity**.
5. Do not manually construct a `JwtAuthenticationToken` from a `userId` value in a message.

Enabling `HttpSession` does not solve identity propagation for schedulers.

## 32. Common anti-patterns

### 32.1. Storing `Authentication` in a static variable

```java
static Authentication currentUser;
```

Do not do this: concurrent requests can overwrite and mix up identities. Use the request context or pass identity explicitly.

### 32.2. Using `JSESSIONID` to access a Bearer-only API

If an API authenticates by Bearer token, a web login cookie does not replace the token. Test `/api/**` routes while the browser is logged in.

### 32.3. Disabling CSRF solely because of `STATELESS`

JWTs in cookies are still automatically sent by browsers. CSRF decisions depend on credential transport.

### 32.4. Using a JWT directly as a session ID

Tokens and session IDs have different lifecycles, validation, revocation, and security semantics.

### 32.5. Sending a refresh token to business APIs

Refresh tokens are only for the token endpoint with a valid OAuth Client, never in place of an access token.

### 32.6. Using `NEVER` and claiming sessions are never read

`NEVER` can still use an existing session; `STATELESS` is the policy that does not use sessions for `SecurityContext`.

### 32.7. Creating a session to reduce JWT verification

If you need to reduce JWKS/introspection network traffic, design a cache honoring the contract. Do not convert a Bearer token into a login session and bypass expiry/audience/revocation.

### 32.8. Forgetting a fallback chain outside `/api/**`

A narrow chain does not automatically protect `/actuator`, `/swagger-ui`, or `/admin`.

### 32.9. Trusting `getSession(false) != null` as proof of login

An existing session does not mean a trustworthy `Authentication` is present.

### 32.10. Assuming web logout revokes JWTs

Tokens copied before logout can remain active until revocation/expiry policies take effect.

## 33. MockMvc test: the next request still requires Bearer

Spring Security Test can create a mock JWT principal:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ApiStatelessTest {

    @Autowired MockMvc mvc;

    @Test
    void bearerAuthenticationDoesNotCarryToNextRequest()
            throws Exception {
        mvc.perform(get("/api/orders/101")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());

        mvc.perform(get("/api/orders/101"))
            .andExpect(status().isUnauthorized());
    }
}
```

This test assumes the controller/service fixture allows the first request to return `200`. **Spring Security Test's `jwt()` usually creates a mock authentication** and **does not run the production `JwtDecoder` to verify a real signed JWT**. It helps verify authorization/chain behavior, not JWT signatures, issuer, audience, and expiry.

To prove **sessions are genuinely unused**, add HTTP tests with real signed tokens, check cookies/sessions, and send requests without Bearer carrying a session cookie from a web login.

## 34. Test matrix for dual web and API chains

| Scenario | Expectation |
| --- | --- |
| `GET /api/orders/101` without Bearer | `401`, no HTML login redirect. |
| API with valid Bearer + `orders.read` | Passes authentication/endpoint policy, still checks owner. |
| API with valid Bearer but missing scope | `403`. |
| Web logged in, calling API with only `JSESSIONID` | Does not replace JWT authentication. |
| Web not logged in, calling `/account` | Appropriate web entry point/login flow. |
| Web logged in, calling `/account` with session cookie | Works per web session policy. |
| Web logged out, reusing old cookie | No longer has web authentication. |
| Bearer token issued before/after web logout | Not automatically revoked without another mechanism. |
| Preflight `OPTIONS /api/orders/101` with allowed origin | CORS handled properly without requiring Bearer on preflight. |
| Non-API URLs like `/actuator` and `/swagger-ui` | Protected by chain/fallback as designed. |

To test real session cookies/redirects, use embedded-server HTTP integration tests or browser tests. Beyond GET, test POST/PUT/DELETE on web session routes to verify CSRF remains enforced.

## 35. JWT integration tests and web session tests must be separated

**JWT end-to-end test:**

1. Prepare a trusted test issuer/JWK Set and a JWT signed with a test private key.
2. Send the Bearer token over HTTP to verify `JwtDecoder`.
3. Verify signature, `iss`, `aud`, `exp`, `nbf`, and authority mapping.
4. Send a request **without Bearer** after a valid request.
5. Send only the web cookie if the app has web sessions; the API must not accept it in place of Bearer.

**Web session integration test:**

1. Log in via form/OIDC Client on the web route.
2. Receive the session cookie.
3. Send the cookie on a subsequent request and verify web authentication.
4. Test CSRF, session fixation, timeout, and invalidation on logout.
5. Verify a browser session cannot bypass the Bearer-only API chain.

Each test proves a different piece: JWT cryptography does not prove web session logic; web session login does not prove the audience of an API access token.

## 36. Diagnosing 200, 401, 403, 302, and CORS errors

| Symptom | Possibility | Investigation |
| --- | --- | --- |
| Request 1 with Bearer gets 200, request 2 without header gets 401 | Client failed to attach Bearer on next request; stateless works as intended. | Inspect HTTP client/interceptor, do not log tokens. |
| Same JWT gets 401 on later request | Token expired/revoked, clock skew, JWKS/issuer/introspection error. | Check decoder, IdP, pod config, and clocks. |
| API request returns `302 /login` | Request hit the web chain or wrong entry point. | Security matcher/order and entry point. |
| API returns 403 with valid JWT | Scope, role, CSRF, or domain policy denied it. | Distinguish rules and CSRF by route. |
| GET works but POST gets 403 from browser | Missing authority or missing CSRF token. | Check credential transport and filter chain. |
| Browser reports CORS error | Preflight/origin/headers rejected. | Check CORS config and OPTIONS flow. |
| Session login only works on one pod | Incorrect session store/sticky routing. | Check HA, Redis/Spring Session, and LB. |
| JWT only works on one pod | Differing JWKS cache, issuer config, version, or clock. | Inspect each pod rather than assuming a session bug. |

Do not log raw access tokens, refresh tokens, `Authorization`, session IDs, or client secrets. Use trace IDs, endpoints, authentication type, issuer alias, and safe-level error reasons.

## 37. Quick selection table by system goal

| Goal | Approach |
| --- | --- |
| REST API for mobile or M2M | `oauth2ResourceServer`, `STATELESS`, Bearer in header, clear `401/403`. |
| Multi-pod scalable JWT API | Stateless authentication and controlled JWKS cache, no sticky login sessions needed. |
| Opaque API needing revocation state | Stateless + introspection; separate timeout/cache/revocation policies. |
| Browser web app with form login | `IF_REQUIRED` or suitable session policy, CSRF, and cookie security. |
| Browser avoiding access tokens in JS | BFF with browser session + server-side token storage; downstream API stays Bearer. |
| Same app hosting web and API | Multiple chains, `@Order`, narrow matchers, and fallback protecting all URLs. |
| Immediate "log out everywhere" across devices | Revocation/session management/token status per product requirements; `STATELESS` alone does not do this. |
| Protecting owner/tenant boundaries | Domain authorization, membership, and scoped data operations; independent of sessions. |

## 38. Decision flow for session management policy

Before building an endpoint:

1. **Who is the caller?** Mobile, browser, BFF, service account, CLI?
2. **How does the credential travel?** Authorization header or auto-sent cookie?
3. **Is this path an OAuth Resource Server or web login/OAuth Client?**
4. **Does login need to be remembered across requests?** If no, `STATELESS`; if yes, manage sessions separately.
5. **Does the app serve both web and API?** Separate `SecurityFilterChain`s and add a fallback.
6. **Does CSRF apply?** Base this on browser credentials, not the session policy name.
7. **Is CORS needed?** Configure origins/preflight for cross-origin SPAs.
8. **How do expiry/refresh/revocation work?** Define separate lifecycles for access tokens, refresh tokens, and sessions.
9. **Does JWT/opaque validation cover issuer/audience/scope?**
10. **Does domain authorization check tenant/owner?**
11. **Do async/background jobs need trusted identity propagation?**
12. **Have you tested a non-Bearer request after a Bearer request and a web cookie against the API?**

```mermaid
flowchart TD
    A["Request arrives at system"] --> B{"Which credential does client send?"}
    B -- "Authorization: Bearer" --> C["JWT/opaque Resource Server"]
    C --> D["Authenticate token per request"]
    D --> E["No login HttpSession needed: STATELESS"]
    E --> F["Check scope, audience, tenant, owner"]
    B -- "Browser session cookie" --> G["Web/BFF login"]
    G --> H["Appropriate session policy, e.g. IF_REQUIRED"]
    H --> I["Cookie security, CSRF, logout, timeout"]
    I --> J{"Need to call downstream API?"}
    J -- "Yes" --> K["BFF sends appropriate access token"]
    K --> C
    J -- "No" --> L["Handle web use case per domain policy"]
```

## 39. Concluding principles

- **Bearer authenticates per request**: Protected APIs must require valid credentials on every call, never relying on IP or prior requests.
- **`SecurityContext` does not mean `HttpSession`**: a context can exist for the scope of a request while the API remains stateless.
- **`STATELESS` and `NEVER` are different**: `NEVER` may use an existing session, whereas `STATELESS` does not use sessions to obtain context.
- **Stateless does not eliminate JWK/introspection caches or cookies created by other components.**
- **JWT and opaque tokens differ in verification mechanism**; both can be used in stateless APIs.
- **CSRF depends on how browsers send credentials**; a JWT in a cookie differs from a Bearer header.
- **A BFF can be stateful while downstream APIs remain stateless**.
- **Logging out of a session does not automatically revoke Bearer tokens**; access token expiry, refresh tokens, and web sessions have separate lifecycles.
- **Multiple `SecurityFilterChain`s must have clear matchers/fallbacks**, preventing web cookies from accidentally being accepted by a Bearer-only API.
- **Test security at the right layers**: real-signed JWTs, no-token requests, web cookies, session login/logout, CSRF/CORS, and domain authorization.

**Key takeaway:** `SessionCreationPolicy.STATELESS` is the natural choice when a **Spring Security Resource Server receives a Bearer access token on each HTTP request** and does not need to restore authentication from `HttpSession`. When browser logins, cookies, or BFFs are involved, manage sessions on **the exact paths that need sessions**, keeping CSRF and session lifecycles aligned; never equate Bearer authentication, web login sessions, token refresh/revocation, and business permissions.
