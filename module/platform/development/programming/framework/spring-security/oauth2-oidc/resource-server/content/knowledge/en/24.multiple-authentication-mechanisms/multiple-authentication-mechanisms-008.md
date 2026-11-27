# Conflicts Between Session Cookies, HTTP Basic, Bearer, and Other Mechanisms

## 1. Opening Scenario: A Single Request with Multiple "Logged-In Signals"

A Spring Boot application serves three user groups:

- **Browsers:** users sign into `/web/**` via form login or OpenID Connect (OIDC), then use a session cookie such as `JSESSIONID`.
- **Mobile/SPA/microservices:** clients call `/api/**` using an OAuth 2.0 **access token** in `Authorization: Bearer ...`.
- **Legacy internal systems:** service-to-service clients call `/internal/legacy/**` with `Authorization: Basic ...` during an OAuth migration period.

A request from a browser may carry both a session cookie and a Bearer token:

```http
GET /api/orders/42 HTTP/1.1
Host: shop.example.com
Cookie: JSESSIONID=<browser-session-cookie>
Authorization: Bearer <oauth-access-token>
Accept: application/json
```

Another request might carry only the cookie:

```http
GET /api/orders/42 HTTP/1.1
Host: shop.example.com
Cookie: JSESSIONID=<browser-session-cookie>
```

If the API is designed **to accept only Bearer access tokens**, the second request must be rejected even if the user is logged into the website. Yet if the API and website share one `SecurityFilterChain` that reads the HTTP session, a session cookie can unexpectedly become a **valid Authentication** for the API.

Even worse, if a request carries an **expired** Bearer token alongside a valid session cookie, a misconfigured chain or custom filter might quietly "fall back" to the cookie and grant access. The API has then bypassed JWT verification, audience, and scopes for the token the client actually presented.

This is the core topic of **conflicts across multiple authentication mechanisms**: not just two filters running together, but deciding **which credential is allowed to establish identity**, **which policy must apply**, **when to reject**, and **never silently switching authentication paths when one credential fails**.

### Questions This Lesson Resolves

1. How do session cookies, HTTP Basic, Bearer, API keys, mTLS, and OIDC login fundamentally differ?
2. With multiple `SecurityFilterChain` beans, which chain does Spring Security pick?
3. What happens if a single chain enables `formLogin`, `httpBasic`, and `oauth2ResourceServer` simultaneously?
4. If a request carries both `JSESSIONID` and a Bearer token, which credential should the system trust?
5. Should Basic be tried when a Bearer token fails, or a session used when a JWT expires?
6. Why does enabling HTTP Basic or cookie authentication change CSRF decisions?
7. How do you ensure APIs return `401 Bearer`, web routes redirect to login, and legacy endpoints return `401 Basic`?
8. How do you configure and test to prevent **credential confusion**, **session fallback**, and **authorization bypasses**?

**Core principle:** Define **one explicit authentication contract per resource area**, allowing or rejecting each credential type deliberately; never infer that "authenticated by any means" grants permission to call every API.

---

## 2. Authentication, Credential, and Authorization Are Three Different Concepts

### 2.1. Credential: The Proof a Client Sends to the Server

An HTTP request may contain:

```http
Authorization: Bearer eyJhbGciOi...
```

or:

```http
Authorization: Basic c2VydmljZTpwYXNzd29yZA==
```

or:

```http
Cookie: JSESSIONID=...
```

or another proof such as an mTLS client certificate, signed request, or API key via a defined header.

These are **different ways of presenting a credential**. They do not themselves answer whether that credential is allowed for the current resource.

### 2.2. Authentication: The System Accepts the Credential and Builds a Principal

Spring Security typically represents the result as an `Authentication` in `SecurityContext`:

- `JwtAuthenticationToken` from a JWT access token.
- `BearerTokenAuthentication` from opaque token introspection.
- `UsernamePasswordAuthenticationToken` from form login or HTTP Basic, depending on provider.
- `OAuth2AuthenticationToken` or an authentication holding an OIDC principal after `oauth2Login`.
- A custom `Authentication` type for API keys/mTLS.

**An authenticated `Authentication` does not prove it was created by the right mechanism for the endpoint being called.**

Example:

```text
GET /api/orders/42
Expected:  JwtAuthenticationToken + SCOPE_orders.read
Observed:  UsernamePasswordAuthenticationToken from browser session
```

If the rule is only `authenticated()`, the request may be allowed even though the API contract requires a Bearer access token.

### 2.3. Authorization: Successful Authentication Can Still Lack Permission

A Bearer JWT with valid signature/issuer/audience yet missing `SCOPE_orders.read` is normally denied at **authorization**, not authentication.

A valid session cookie for a user with `ROLE_USER` does not grant the `orders.read` scope either. An API requires token permissions or a specific business policy, not merely checking that a user exists.

### 2.4. Comparison Table of Mechanisms

| Mechanism | Credential sent by client | Typical Authentication | Key characteristics |
|---|---|---|---|
| Browser session | `Cookie: JSESSIONID=...` | User from `SecurityContext` in session | Browser automatically sends cookies matching cookie scope |
| HTTP Basic | `Authorization: Basic ...` | Verified username/password | Credential can be re-sent per request; Basic is only Base64-encoded |
| OAuth Bearer JWT | `Authorization: Bearer ...` | `JwtAuthenticationToken` | Must verify signature/issuer/audience/expiration/token profile |
| OAuth Bearer opaque | `Authorization: Bearer ...` | `BearerTokenAuthentication` | Typically introspected with AS; must check `active` and policy |
| OIDC browser login | Redirect/code flow, then web session | OIDC user/client authentication | Browser login **does not** mean the API received a Bearer token |
| API key | `X-API-Key` or defined scheme | Custom Authentication | Needs client ID, rotation, scopes, rate limits, secret protection |
| mTLS client authentication | TLS client certificate + proof of key possession | X.509/client identity | Proves sender holds private key; still needs authorization |
| Gateway identity header | `X-Authenticated-User` from trusted gateway | Principal from proxy policy | Must strip client-sent headers and verify proxy boundary |

Never treat these mechanisms as equal in strength or semantics. Each mechanism has its own revocation, credential protection, and policy model.

---

## 3. What to Know About Each Credential Type

### 3.1. Session Cookies: Sent Automatically by Browsers

After web login, the server may send:

```http
HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=<opaque-session-id>; Path=/; HttpOnly; Secure; SameSite=Lax
Location: /web/dashboard
```

The browser sends the cookie on requests matching `Domain`, `Path`, `Secure`, and `SameSite`. Client JavaScript does not have to attach the Cookie header explicitly; that is why **session-based authentication generally requires CSRF protection** for state-changing operations.

On the same hostname `shop.example.com`, a cookie with `Path=/` can also appear on `/api/**` requests. The cookie's **presence** does not mean the API should **use the cookie for authentication**.

### 3.2. HTTP Basic: Neither Session Nor Bearer

Example:

```http
Authorization: Basic c2VydmljZS1yZWFkZXI6ZGVtby1vbmx5
```

The Base64 value represents a `username:password` string. Base64 **is not security encryption**; HTTPS is mandatory, and avoid logging the header.

HTTP Basic is typically sent on every request. Some browsers can **cache Basic credentials per protection space and resend them automatically**, so when HTTP Basic is accepted in browsers, evaluate **CSRF and automatic credential-sending risks** just like other ambient authentication mechanisms.

Basic has no OAuth `scope`/`audience` semantics. If an API uses Basic for a legacy client, define its roles/permissions and credential lifecycle explicitly rather than treating a password as an access token.

### 3.3. Bearer Access Tokens: Anyone Holding the Token Can Present It

In OAuth 2.0 Bearer token usage:

```http
Authorization: Bearer <access-token>
```

The Resource Server verifies the token per contract. JWTs can be decoded/verified with `JwtDecoder`; opaque tokens are typically checked via `OpaqueTokenIntrospector`.

When clients explicitly attach the Authorization header, browsers **do not automatically attach an access token just because the user signed in with a session**. However, if a system stores a Bearer token **in a cookie** and has the server extract it automatically, the credential becomes an ambient credential and the CSRF risk changes; never assume "Bearer always means CSRF-exempt".

### 3.4. OIDC Login: The Web App Is an OAuth2/OIDC Client

When using:

```java
.oauth2Login(Customizer.withDefaults())
```

the application runs an authorization code flow with the IdP to log users into the website. It can create a web session and store an `OAuth2AuthenticationToken`/OIDC principal.

**An OIDC ID token is not an access token for a Resource Server.** An ID token normally has the OAuth Client ID as its audience, whereas an access token for `orders-api` must satisfy the API's audience and scopes.

### 3.5. API Keys or mTLS Are Separate Contracts

If adding an API key or mTLS to an endpoint accepting Bearer tokens, answer:

- Are API key and Bearer interchangeable?
- Do they grant the **same set of permissions** or restricted permissions?
- When both appear, are both required, or just one?
- If one credential is rejected, may the other credential be used?
- Which principal is used for logging, authorization, and tenant scoping?
- When one credential is revoked, can the other be used to bypass revocation?

**Never enable an extra authentication filter and let the answers depend accidentally on filter order.**

---

## 4. Why Do Conflicts Arise in Spring Security?

### 4.1. Filters Have Different Responsibilities

In Spring Security Servlet, depending on configuration, a chain may include:

- Security context filters: load/save `SecurityContext`.
- `UsernamePasswordAuthenticationFilter`: handles form login.
- `BasicAuthenticationFilter`: handles HTTP Basic.
- `BearerTokenAuthenticationFilter`: handles OAuth Bearer tokens.
- `ExceptionTranslationFilter`: translates downstream security exceptions into entry point/denied handler responses.
- `AuthorizationFilter`: enforces `authorizeHttpRequests`.

A request can pass through **multiple filters in the same chain**. Each filter has its own trigger condition: the Basic filter looks at Basic headers, the Bearer filter looks at Bearer headers, and the form login filter watches the login processing URL. The security context filter may restore session authentication before those filters run.

**Do not assume every filter tries every credential in a framework-guaranteed fallback order.** Ordering, error handlers, request matchers, and `SecurityContextRepository` determine actual behavior.

### 4.2. AuthenticationManager Does Not Resolve Cookie/Basic/Bearer Priority

`AuthenticationManager` can use multiple `AuthenticationProvider` instances, yet it typically processes **one Authentication request type already created by a filter**. It does not decide how a session cookie and a Bearer token in the same HTTP request should be combined.

Example:

```text
BasicAuthenticationFilter
  → UsernamePasswordAuthenticationToken
  → AuthenticationManager / password provider

BearerTokenAuthenticationFilter
  → BearerTokenAuthenticationToken
  → AuthenticationManager / JWT or opaque provider
```

If both session and Bearer are present, deciding which to trust is not just a provider-selection problem; it requires **chain boundary and credential policy design**.

### 4.3. Enabling Three Mechanisms in One Chain Creates Unpredictable Results

An unseparated example:

```java
@Bean
SecurityFilterChain mixed(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/**").authenticated()
            .requestMatchers("/web/**").authenticated()
            .anyRequest().denyAll())
        .formLogin(Customizer.withDefaults())
        .httpBasic(Customizer.withDefaults())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

This configuration is **not always technically invalid**. However, if the product requires APIs to **use Bearer only** and the web UI to **use sessions only**, it fails to express that boundary.

Risks:

- `authenticated()` on the API may be satisfied by a web session if the chain still reads session context.
- HTTP Basic can become an unexpected alternative auth path on unintended resources.
- Requests missing Authentication may get redirects or Basic challenges instead of a Bearer challenge.
- Disabling CSRF to "fix an API 403" weakens web sessions and Basic in browsers.
- Bad tokens or conflicting credentials can produce inconsistent error semantics.
- Roles/authorities from one mechanism can accidentally satisfy rules meant for another.

A better default solution is **separating URL zones by mechanism**.

---

## 5. `SecurityFilterChain`: First Matching Chain Wins

### 5.1. FilterChainProxy Does Not Stack Every Chain

Spring Security Servlet uses `FilterChainProxy` to pick a `SecurityFilterChain` for an HTTP request. With multiple chains, the framework picks **the first chain whose `RequestMatcher` matches** in priority order.

Example:

```text
@Order(1)  /api/**               → OAuth Bearer only
@Order(2)  /internal/legacy/**   → HTTP Basic only
@Order(3)  any request          → Browser session/form login
```

Flow:

```mermaid
flowchart TD
    R["HTTP request"] --> P["FilterChainProxy"]
    P --> M1{"Matches /api/**?"}
    M1 -->|Yes| A["API chain: JWT/opaque Bearer, stateless"]
    M1 -->|No| M2{"Matches /internal/legacy/**?"}
    M2 -->|Yes| L["Legacy chain: HTTP Basic, route-restricted"]
    M2 -->|No| W["Web catch-all: form/OIDC login, session + CSRF"]
    A --> Z["Authorization and business logic if valid"]
    L --> Z
    W --> Z
```

**Spring Security never falls through to the web chain after API Bearer authentication fails.** Once a request matches the API chain, errors are handled inside that chain.

### 5.2. `securityMatcher` Selects the Chain; `requestMatchers` Selects Policy Inside the Chain

Example:

```java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().denyAll());
```

- `securityMatcher("/api/**")` decides whether the entire filter chain handles the request.
- `requestMatchers("/api/public/**")` decides URL authorization **after the API chain has been chosen**.
- `anyRequest().denyAll()` applies **only** to requests matching that chain; it does not protect all URLs in the application.

A chain without its own `securityMatcher` normally matches every request, so placing a catch-all before the API chain prevents the API chain from ever running.

### 5.3. `@Order` Must Be Declared Deliberately

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception { ... }

@Bean
@Order(2)
SecurityFilterChain legacy(HttpSecurity http) throws Exception { ... }

@Bean
@Order(3)
SecurityFilterChain web(HttpSecurity http) throws Exception { ... }
```

Do not rely on method declaration order in the source file. `@Order` controls **chain evaluation order**, not filter order within a chain.

### 5.4. The Final Catch-All Should Not Be a Global `permitAll()`

If the final web chain has:

```java
.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll())
```

a new endpoint outside `/api/**` or `/internal/legacy/**` can unexpectedly become public.

It is safer to explicitly allow static/login endpoints, require login for web areas, and **deny by default** for other URLs. Security filters such as form login/logout have their own endpoints and must sit within the chain that configures those mechanisms.

---

## 6. Recommended Rule: One Primary Authentication Mechanism per URL

A clear contract:

| URL zone | Allowed mechanism | Non-substitutable mechanisms | Response when credential missing |
|---|---|---|---|
| `/api/**` | OAuth Bearer access token | Web session, HTTP Basic, unknown API key | `401` Bearer challenge |
| `/internal/legacy/**` | HTTP Basic for authorized service | Bearer, web session | `401` Basic challenge |
| `/web/**` | Browser session after form/OIDC login | Direct Bearer, Basic | Login redirect |
| `/login`, `/logout` | Browser login/logout flow | API Bearer token | Per web login policy |
| `/assets/**` | No login required | No "fallback" needed | Public static resource |
| `/api/public/**` | Public, per contract for handling Bearer | Never elevates privileges | Normally allowed if no bad token sent |

This contract is not mandatory for every organization, yet **an equivalent explicit table should exist** before writing filters.

### 6.1. What If a Request Sends the "Wrong Kind" of Credential?

If `/api/**` accepts only Bearer and a client sends:

```http
Authorization: Basic dXNlcjpwYXNz
```

the Basic filter **is not enabled in the API chain**. The request is treated as **lacking Bearer authentication**, and a protected API returns `401 Bearer`.

That does not mean the Basic service account password is wrong; it is simply **not a credential accepted by the API**.

Similarly, if the legacy chain accepts only Basic and a client sends Bearer, do not attempt to decode the Bearer token and grant legacy access.

### 6.2. A Presented Invalid Credential Must Fail, Not Fall Back

An API request:

```http
Cookie: JSESSIONID=<valid-web-session>
Authorization: Bearer <expired-access-token>
```

The right outcome for a Bearer-only API is **rejecting the token**, typically `401 invalid_token`. Never use the session to let it pass.

For a legacy Basic endpoint:

```http
Cookie: JSESSIONID=<valid-web-session>
Authorization: Basic <wrong-password>
```

Basic authentication must fail per policy. Never use the web session as a rescue path.

### 6.3. Do Not Equate "Same User" with "Same Credential"

A user signed into the web UI while holding a JWT access token with the same `sub`:

```text
Web session:
  user = alice
  roles = ROLE_USER

Bearer access token:
  sub = alice
  aud = orders-api
  scope = orders.read
```

Even with the same identity, the two credentials differ in lifecycle, audience, scopes, and revocation. Never substitute a session for an API credential just because `principal.getName()` matches.

---

## 7. Matrix of Credential Combinations

Suppose `/api/orders/42` requires a Bearer token with `SCOPE_orders.read`, and the API chain genuinely does not read session authentication.

| Session cookie | Authorization header | API chain interpretation | Typical result |
|---|---|---|---|
| No | No | Missing Bearer | `401 Bearer` |
| Yes, valid | No | Still missing Bearer | `401 Bearer` |
| No | Valid Basic for legacy | Wrong authentication scheme | `401 Bearer` |
| Yes, valid | Valid Basic | Basic does not replace Bearer | `401 Bearer` |
| No | Valid Bearer JWT, right scope | Authentication + authorization pass | Endpoint executes |
| Yes, valid | Valid Bearer JWT, right scope | Uses Bearer; ignores session for privileges | Endpoint executes |
| Yes, valid | Expired Bearer JWT | JWT validation fails | `401 invalid_token` |
| Yes, valid | Bearer token wrong audience | JWT validator rejects | `401` |
| No | Valid Bearer, missing scope | Authentication passes, authorization denies | `403` |
| Yes, valid | Valid Bearer, missing scope | Cookie does not add permissions | `403` |
| No | Malformed Bearer header | Resolver rejects request | Possibly `400 invalid_request` |
| Yes, valid | Valid Bearer, wrong tenant | Business authorization denies | `403`/`404` per policy |

Exact status codes depend on filters/handlers and application policy, yet **permission outcomes must be consistent**: cookies/Basic never bypass Bearer requirements.

For the web chain, outcomes differ:

| Request to `/web/dashboard` | Web session | Other header | Result |
|---|---|---|---|
| No cookie | Not logged in | No Bearer | Redirect to login |
| Valid cookie | Logged in | No Bearer | Allowed |
| Valid cookie | Logged in | Invalid Bearer JWT | Web chain has no Resource Server, so JWT header neither logs user in nor breaks session |
| No cookie | Not logged in | Valid Bearer | Does not turn Bearer into a web session; usually redirects to login |
| No cookie | Not logged in | Valid Basic | Does not auto-login if web chain disables Basic |

**The presence of an unused credential** is not proof a user may access a URL. When stricter conflict detection is required, the system can proactively reject requests carrying multiple credential types instead of merely ignoring unsupported ones.

---

## 8. Two Authorization Schemes in One Request: Basic and Bearer Cannot Be Arbitrarily Combined

### 8.1. One Authorization Header Represents One Credential Scheme

Valid individually:

```http
Authorization: Basic c2VydmljZTpwYXNzd29yZA==
```

or:

```http
Authorization: Bearer eyJhbGciOi...
```

Do not combine them:

```http
Authorization: Basic c2VydmljZTpwYXNzd29yZA==, Bearer eyJ...
```

expecting Spring Security to parse two independent credentials and pick the stronger one. That is not how a standard Bearer or Basic credential is represented.

### 8.2. Multiple Authorization Headers Create Ambiguity

Example:

```http
GET /api/orders/42 HTTP/1.1
Authorization: Basic <basic-credential>
Authorization: Bearer <bearer-token>
```

Reverse proxies, Servlet containers, and frameworks handle duplicate headers differently—reading the first value, concatenating, or rejecting. If gateway and backend **interpret them differently**, authentication confusion can arise.

**Safe design:** In zones requiring one primary credential, normalize or reject duplicate/malformed Authorization headers at a consistent boundary. Never assume `request.getHeader("Authorization")` always reflects every value sent.

### 8.3. Custom Detection Must Consider Both Gateway and Backend

A `OncePerRequestFilter` can count `Authorization` values seen by the Servlet and reject invalid requests. Illustrative example:

```java
package com.example.security;

import java.io.IOException;
import java.util.Collections;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.web.filter.OncePerRequestFilter;

public class DuplicateAuthorizationHeaderFilter
        extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        int headerCount = Collections.list(
            request.getHeaders(HttpHeaders.AUTHORIZATION)).size();

        if (headerCount > 1) {
            response.sendError(
                HttpServletResponse.SC_BAD_REQUEST,
                "Multiple Authorization headers are not supported");
            return;
        }

        chain.doFilter(request, response);
    }
}
```

This illustrates **the principle**, not a complete defense against every form of header smuggling. If a proxy already folded headers into one value before the Servlet, the filter sees only one value. You need consistent normalization rules across gateway/ingress and HTTP server.

When adding a custom filter to Spring Security, place it inside the right API chain or gateway policy; never register a global Servlet filter carelessly that alters web login or fails to run ahead of proxies.

### 8.4. Do Not Fix This by "Trying All and Picking the Successful Credential"

Unsafe pseudo-code:

```text
if bearer is valid:
    use bearer
else if basic is valid:
    use basic
else if session exists:
    use session
```

When Bearer expires or is revoked, a client can still use Basic/session to bypass token limits. If the business genuinely needs **one of several mechanisms**, define explicit authorization policies, precedence, error handling, and scope—not a "try until one succeeds" loop.

---

## 9. Recommended Architecture: Separating Chains for API Bearer, Legacy Basic, and Browser Session

### 9.1. Gradle Dependencies

Spring Boot Servlet example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The following example uses Spring Security with `SecurityFilterChain` and lambda DSL; adjust for your actual Spring Boot/Spring Security version. For WebFlux, refer to the `SecurityWebFilterChain` equivalents.

### 9.2. Issuer Configuration for JWT API

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/shop
```

The issuer is a placeholder. The API must verify signature, issuer, expiration, and **`orders-api` audience** per the token contract. If using opaque tokens, replace the JWT configuration with appropriate introspection.

### 9.3. Three Explicit `SecurityFilterChain` Beans

```java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class MultiMechanismSecurityConfig {

    // REST API: accepts OAuth Bearer access tokens only.
    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(cache -> cache.disable())
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .logout(logout -> logout.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }

    // Legacy service endpoint: Basic only, read-only in this example.
    @Bean
    @Order(2)
    SecurityFilterChain legacyBasic(HttpSecurity http)
            throws Exception {

        return http
            .securityMatcher("/internal/legacy/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(cache -> cache.disable())
            .formLogin(form -> form.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/internal/legacy/**")
                    .hasRole("LEGACY_READER")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    // Browser website: session + form login, final catch-all.
    @Bean
    @Order(3)
    SecurityFilterChain browserWeb(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/assets/**",
                    "/favicon.ico",
                    "/error",
                    "/login")
                    .permitAll()
                .requestMatchers("/web/admin/**")
                    .hasRole("WEB_ADMIN")
                .requestMatchers("/web/**")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.permitAll())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll())
            .build();
    }
}
```

**Understand each decision in this configuration:**

1. `@Order(1)` has matcher `/api/**`; every API request enters a chain **enabling only Bearer JWT**.
2. The API chain disables `httpBasic` and `formLogin` so they cannot act as fallbacks.
3. `STATELESS` and `NullSecurityContextRepository` prevent the API chain from using HTTP sessions as SecurityContext authentication. `requestCache.disable()` prevents saving API requests for web login redirects.
4. `csrf.disable()` applies only to the API chain, assuming the API is **purely Bearer-header** and accepts no browser-auto-sent credentials.
5. The legacy chain accepts only Basic and **only read-only GET** in this lesson; therefore disabling CSRF for Basic by default is not recommended. If adding Basic POST/PUT/DELETE, evaluate CSRF and restrict clients capable of auto-sending credentials.
6. The web chain is last/catch-all, using sessions and form login; **CSRF is not disabled**.
7. `anyRequest().denyAll()` blocks out-of-policy paths in every chain.
8. Basic configuration here does not auto-create users; an appropriate `UserDetailsService`/authentication provider is needed.
9. Routes `/api/orders/**`, `/web/**`, and `/internal/legacy/**` must have matching Controllers to return 2xx when security permits.

**This is an illustrative configuration of three separated URL zones.** If your app uses OAuth2 login or different CSRF cookies, adapt to your contract; never register a competing catch-all chain at the same time.

### 9.4. Why Use `NullSecurityContextRepository` on the API?

`SessionCreationPolicy.STATELESS` tells Spring Security not to create/use `HttpSession` to obtain SecurityContext for API authentication. Adding `NullSecurityContextRepository` makes the boundary explicit: **never load or save Authentication from sessions in the API chain**.

It does not stop browsers from sending Cookie headers. Nor does it block custom code that intentionally reads `HttpSession`. Avoid custom filters like:

```java
HttpSession session = request.getSession(false);
if (session != null && session.getAttribute("user") != null) {
    allowApiRequest();
}
```

Putting that logic in the API request flow means your own application code breaks the Bearer-only boundary.

### 9.5. Why Not Disable CSRF in the Legacy Basic Chain?

HTTP Basic credentials can be cached and re-sent automatically by browsers in certain contexts. If a Basic endpoint supports state-changing operations triggerable by a browser, it **carries CSRF risk**.

The legacy chain example allows only `GET`, and Spring Security's default CSRF does not block GET since it must be a side-effect-free read method. If the product needs Basic for POST/DELETE, do not fix it by blindly disabling CSRF; evaluate request-proof mechanisms, client origins, and proper network/CSRF protection.

### 9.6. The Web Chain Must Cover `/login` and `/logout`

With `formLogin`, `GET /login` and `POST /login` may be handled by Spring Security rather than your own Controller. If the web chain only matches `/web/**`, login endpoints can fall outside the chain.

Having the final catch-all covers those endpoints. If you want a narrow matcher for the web chain, add the corresponding login/logout/OIDC callback URLs to the matcher.

---

## 10. Provisioning Test Accounts for Basic and Form Login

### 10.1. `UserDetailsService` for Lab Examples

```java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUserConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        return new InMemoryUserDetailsManager(
            User.withUsername("legacy-reader")
                .password(encoder.encode("demo-legacy-password"))
                .roles("LEGACY_READER")
                .build(),
            User.withUsername("web-user")
                .password(encoder.encode("demo-web-password"))
                .roles("WEB_USER")
                .build());
    }
}
```

These are **mock credentials for learning environments**, not recommended production passwords/secrets.

### 10.2. Does Sharing One `UserDetailsService` Cause Fallback?

Two chains can share a `UserDetailsService`, yet that **does not automatically make web sessions accepted in the API Bearer chain**. The boundary lives in each chain's **authentication filters/session context and authorization policy**.

However, letting legacy Basic and website form login share the same username/password store may be unsuitable for security and lifecycle reasons. In real deployments, separate service accounts from human users, restrict privileges, and plan to retire Basic.

### 10.3. Do Not Grant API Access Based on a Basic User's Role

`legacy-reader` has `ROLE_LEGACY_READER`. That does not grant `SCOPE_orders.read`, and the API Bearer chain still requires an access token.

Conversely, a Bearer token with `SCOPE_orders.read` does not become a valid Basic username/password on the legacy endpoint.

---

## 11. Ensuring the JWT Was Issued for the Right API, Not Just the Right Issuer

### 11.1. The Same Authorization Server Can Issue Tokens for Multiple APIs

Example JWT payload:

```json
{
  "iss": "https://id.example.com/realms/shop",
  "sub": "user-417",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
```

It may be validly signed and unexpired, yet `orders-api` **must not accept it** because it is meant for `billing-api`.

Never treat separating into a Bearer-only chain as an excuse to skip issuer/audience validation.

### 11.2. `JwtDecoder` Bean with an Audience Validator

Example when configuring the decoder explicitly:

```java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer =
            "https://id.example.com/realms/shop";

        // JWKS URI approved in server configuration.
        String jwksUri =
            "https://id.example.com/realms/shop/protocol/openid-connect/certs";

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder
                .withJwkSetUri(jwksUri)
                .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Audience not accepted",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audience));

        return decoder;
    }
}
```

This is a **custom decoder bean replacing auto-configuration**, not something you must add when auto-configuration already meets every requirement. Specify the JWKS URI, allowed signing algorithms, issuer, audience, and token profile per the AS contract.

If using a Spring Boot version providing the corresponding audience property, you can configure via properties, while **verifying actual behavior for your version**. Avoid assuming `issuer-uri` alone always enforces audience.

### 11.3. An OIDC Login ID Token Does Not Replace a Bearer Access Token

After website login, an ID token typically has:

```json
{
  "iss": "https://id.example.com/realms/shop",
  "aud": "web-client-id",
  "sub": "user-417"
}
```

Do not send this ID token to `orders-api`. The API needs an **OAuth access token** with the right recipient and `orders.read` permission.

### 11.4. Scopes Must Be Checked After Authentication

A valid Bearer JWT:

```json
{
  "iss": "https://id.example.com/realms/shop",
  "aud": ["orders-api"],
  "sub": "user-417",
  "scope": "profile.read"
}
```

still lacks `SCOPE_orders.read`. `hasAuthority("SCOPE_orders.read")` will deny it, typically `403 Forbidden`. This is not an error where a session cookie should be used to "upgrade permissions".

---

## 12. If the API Uses Opaque Tokens Instead of JWTs

Chain separation does not require access tokens to be JWTs. The API can introspect opaque tokens instead of decoding them:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

And inside the API chain, replace:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults()))
```

with:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults()))
```

These are **two alternatives depending on the token contract**—not something where enabling both DSLs lets Spring Security automatically guess which issuer owns a token in every configuration.

### 12.1. `active=true` Does Not Make a Token Universally Valid

An introspection response:

```json
{
  "active": true,
  "aud": ["billing-api"],
  "scope": "orders.read",
  "sub": "user-417"
}
```

is still inappropriate for `orders-api` if the API requires that audience. Enforce this via an `OpaqueTokenIntrospector` decorator or an AS–Resource Server contract guaranteeing audience binding.

### 12.2. Introspection Failures Must Not Fall Back to Sessions

If the AS times out, fails TLS, or returns `active=false`, a Bearer-only API **must not grab a session cookie or Basic user** to treat the request as authenticated.

Distinguish:

- `active=false`: token rejected by AS, typically `401`.
- AS unreachable: upstream verification failure; status may be 5xx/challenge per handler, but never grant access.
- Valid token missing scope: typically `403`.
- Valid token with scope but wrong tenant: deny per business policy.

---

## 13. Web Login via OIDC: Replacing Form Login While Keeping the Session Boundary

If the website uses `oauth2Login` instead of internal username/password, add the OAuth2 Client starter:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
```

Example Client registration:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://id.example.com/realms/shop
```

You can update `browserWeb(...)` in the three-chain setup to use:

```java
.oauth2Login(Customizer.withDefaults())
```

instead of:

```java
.formLogin(form -> form.permitAll())
```

Common URLs:

```text
/oauth2/authorization/company
/login/oauth2/code/company
```

must be handled by **the web chain containing `oauth2Login`**. If the web chain only matches `/web/**`, callbacks may not be processed.

### 13.1. OIDC Login Does Not Switch the API to Session Authentication

Diagram:

```mermaid
sequenceDiagram
    participant B as Browser
    participant WEB as Web chain / OIDC Client
    participant OP as OIDC Provider
    participant API as Bearer API chain

    B->>WEB: GET /web/dashboard
    WEB-->>B: 302 to OIDC login
    B->>OP: Authorization request
    OP-->>B: Redirect code + state
    B->>WEB: GET /login/oauth2/code/company?code=...
    WEB->>OP: Exchange code, validate OIDC
    OP-->>WEB: Tokens per OIDC client contract
    WEB-->>B: Session cookie + web redirect
    B->>WEB: GET /web/dashboard + cookie
    WEB-->>B: Authenticated web page
    B->>API: GET /api/orders/42 + cookie, no Bearer
    API-->>B: 401 Bearer
```

**A user logged into an IdP with a web session does not automatically present a valid OAuth access token to the Resource Server.**

### 13.2. Backend-for-Frontend (BFF) Is an Intentional Choice

If browsers should not hold access tokens, the web backend can accept the session cookie, check CSRF/authorization, and use a **server-side authorized client** to obtain/send access tokens to downstream APIs:

```text
Browser
  → /web/orders + session cookie
     → Web/BFF checks session + CSRF + tenant
        → Backend calls orders-api
           Authorization: Bearer <access-token-for-orders-api>
```

These are **two HTTP hops, two trust contracts**. Never use the web `SecurityContext` to bypass the Resource Server API inside the same application.

The backend must manage tokens with the right audience/scope, expiry, refresh, rotation, and logout per contract; never send ID tokens as access tokens.

---

## 14. `401`, `403`, `302`, and `WWW-Authenticate` with Multiple Mechanisms

### 14.1. Why Do APIs Want `401 Bearer`?

For a protected Resource Server endpoint without a token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

When a token is rejected:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

An authenticated Bearer token lacking scope may receive:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Header parameters/realms vary by Spring Security version, exception, and custom handlers. Missing tokens normally omit `invalid_token` because no token failed verification.

### 14.2. Legacy Basic Wants a Different Challenge

If a client calls `/internal/legacy/status` without Basic credentials:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

The actual realm depends on HTTP Basic entry point configuration. Clients may pop up a Basic authentication dialog upon seeing this challenge, especially browsers.

You do not want the Bearer API route returning a `Basic` challenge just because another legacy chain exists in the app.

### 14.3. Websites Typically Redirect

With form login, a request:

```http
GET /web/dashboard HTTP/1.1
```

when unauthenticated may receive:

```http
HTTP/1.1 302 Found
Location: /login
```

The HTTP status may be another redirect type depending on config, yet semantically distinct from an API's Bearer challenge.

### 14.4. When One Chain Supports Both Basic and Form Login

Spring Security can select an `AuthenticationEntryPoint` based on request matchers/content negotiation and exception handling configuration. For instance, browsers get redirects while API clients get Basic challenges in certain configurations.

**Never use `Accept: application/json` or `User-Agent` as a primary security boundary.** Those are client-editable headers. Any URL/API needing a consistent authentication mechanism must be separated by clear matchers/chains or have an explicit entry point policy.

### 14.5. A Server Can Send Multiple Challenges, But That Does Not Imply Automatic Fallback

Under HTTP authentication, a response may include multiple `WWW-Authenticate` challenges if a resource supports multiple schemes. Yet advertising Basic + Bearer **does not automatically define**:

- Which credential takes precedence.
- How requests carrying both are handled.
- Which scheme grants which permissions.
- Whether a session can be substituted instead.

If a system supports multiple schemes on the same endpoint, define all those rules upfront rather than treating challenges as a complete authorization contract.

### 14.6. Quick Status Table

| Address | Error/condition | Typical response |
|---|---|---|
| `/api/orders/42` | Missing Bearer | `401` + `WWW-Authenticate: Bearer` |
| `/api/orders/42` | Malformed Bearer | Possibly `400 invalid_request` |
| `/api/orders/42` | Expired/bad-signature Bearer JWT | `401 invalid_token` |
| `/api/orders/42` | Valid Bearer missing scope | `403` |
| `/api/orders/42` | Basic only | `401 Bearer` |
| `/api/orders/42` | Web session only | `401 Bearer` |
| `/internal/legacy/status` | Missing Basic | `401 Basic` |
| `/internal/legacy/status` | Wrong password | `401 Basic` |
| `/internal/legacy/status` | Bearer only | `401 Basic` |
| `/web/dashboard` | Not logged in | Redirect `/login` |
| `/web/dashboard` | Valid web session | Allowed per web rules |
| `/web/profile` POST | Valid session, missing CSRF | Typically `403` |
| `/api/orders/42` | Valid Bearer, order outside tenant | `403`/`404` per policy |

---

## 15. CSRF: Why Mixing Cookies, Basic, and Bearer Changes the Attack Surface

### 15.1. CSRF Depends on Whether Credentials Are Auto-Sent by Browsers

Suppose a browser signed into a website via `JSESSIONID`. An external site can try to cause the browser to send a state-changing request to that website. Because cookies follow browser sending rules, the server needs CSRF defenses to verify intent.

With HTTP Basic, browsers can cache and auto-send credentials within the protection space after the user authenticates. Thus Basic **is not CSRF-exempt by default**.

For an API accepting only **Bearer tokens in the `Authorization` header actively attached by client code**, an external site cannot read or attach the token. That is why many Bearer-only REST APIs can disable CSRF. However, if the token sits in an auto-sent cookie or the API also accepts sessions/Basic, that assumption breaks.

### 15.2. Example Risky Configuration

```java
http
    .csrf(csrf -> csrf.disable())
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

If this chain protects both website sessions and the API, disabling CSRF here can expose web actions to CSRF via ambient credentials.

### 15.3. Separating CSRF Along Boundaries

In the three-chain example:

- Bearer-only API: `csrf.disable()` inside the API chain when the contract allows.
- Web session: **keep CSRF enabled by default**.
- Legacy Basic: read-only in the example; if adding write endpoints, assess CSRF, especially if browsers can auto-send Basic.

**Never disable CSRF application-wide just because a POST endpoint returned 403 during testing.** The web POST may simply be missing a CSRF token, meaning the denial was right.

### 15.4. SameSite and CORS Do Not Replace CSRF

`SameSite` reduces certain cross-site cookie transmissions, yet is not a complete CSRF solution. Same-site cross-origin contexts, subdomains, and redirect workflows complicate cookie behavior.

CORS governs whether browsers may read responses and perform cross-origin requests under policy. It **does not verify whether the user intended to modify data**.

### 15.5. How Does Basic Protect Write Operations?

If a system must use Basic for POST/PUT/DELETE, weigh options against the threat model:

- Restrict to machine clients on network/private API surfaces not serving browsers.
- Do not rely on CORS to block non-browser clients.
- Enable CSRF tokens if browsers can reach the endpoint with ambient credentials.
- Move to OAuth Client Credentials/mTLS when feasible.
- Scope credentials, rate-limit, audit, and rotate.

There is no universal "Basic + CSRF disabled is always safe" rule across deployments.

---

## 16. Session State and SecurityContext: The Easiest Place to Leak Privileges

### 16.1. A Present Cookie Differs from a Session Used for Authentication

A request:

```http
GET /api/orders/42 HTTP/1.1
Cookie: JSESSIONID=<web-cookie>
```

can hit the API chain. The browser still sends the cookie because `Path=/`, yet the API chain **must not restore web Authentication from the session** in a Bearer-only architecture.

The trio in our example:

```java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.securityContext(context -> context
    .securityContextRepository(
        new NullSecurityContextRepository()))
.requestCache(cache -> cache.disable())
```

makes the intent explicit:

- Never read sessions as SecurityContext for the API.
- Never persist Bearer SecurityContext into sessions.
- Never create request caches for web login redirects from APIs.

### 16.2. `STATELESS` Does Not Strip Cookies from HTTP Requests

`STATELESS` does not make the HTTP container drop `Cookie`, nor does it prevent a custom Filter, Controller, or library from calling `request.getSession()`.

Audit internal middleware carefully for anything that:

- Reads `session.getAttribute("user")` and builds an Authentication.
- Reads `X-User` from a proxy without verification.
- Saves JWT Authentication into the session.
- Uses a ThreadLocal/static variable holding the previous request's user.
- Implements "fallback: if JWT fails, use session".

### 16.3. Saving Bearer Authentication into a Session Breaks Lifecycle Boundaries

In a mixed chain, a Bearer request could persist Authentication into a session if custom persistence is unchecked. The next request without a Bearer header would still appear logged in.

For an API requiring a token on every request, that violates the contract. Use proper session policies and security context repositories, and avoid custom code accidentally turning Bearer Authentication into a web login.

### 16.4. SecurityContextHolder Is Per-Request/Thread, Not User-Global

In Servlet, `SecurityContextHolder` typically uses ThreadLocal. Spring Security manages setting/clearing the context in the filter chain.

Never create a static field like:

```java
static Authentication lastAuthenticatedUser;
```

to "share" a Basic/Bearer user into another Controller. That mixes identities across requests.

### 16.5. Web Login/Logout Does Not Equal Token Revocation

Deleting `JSESSIONID` or invalidating an HTTP session ends only the web session. An unexpired Bearer JWT **is not automatically revoked** when a user logs out of the website.

Conversely, an expired Bearer token does not automatically clear a web session if the website uses cookie login.

When a product requires "logout everywhere", define the link between web sessions, IdP sessions, OAuth access/refresh tokens, and revocation policies. Never rely on a `/logout` endpoint as an automatic kill switch for all credentials.

---

## 17. If the Product Genuinely Wants Multiple Mechanisms on the Same URL

Some transitioning systems need `/api/**` to accept both Basic and Bearer. That can be implemented, provided you **define the contract before enabling filters**.

### 17.1. Mandatory Questions

1. **Do schemes carry equal privileges?** Basic might be read-only while Bearer is read/write.
2. **Which scheme is allowed per HTTP method?** Perhaps Basic is GET-only.
3. **Are session cookies used?** If not, the chain must be stateless.
4. **When a request carries both cookie and Bearer, what happens?** Ignore the cookie or reject as a credential conflict?
5. **If Bearer is invalid, is Basic tried?** Reject rather than silently switching auth paths.
6. **If a client sends two Authorization headers, what happens?** Usually reject.
7. **Does CSRF apply?** Basic can act as an ambient credential in browsers.
8. **Which principal drives rate limits/auditing?** User or service account?
9. **How will Basic be retired after migration?** Are there a sunset date and usage metrics?

### 17.2. Prefer Splitting URLs or Versioning Surfaces

Instead of accepting both Basic and Bearer at the same URL:

```text
/internal/legacy/orders/**  → Basic
/api/orders/**              → Bearer
```

helps:

- Define clear entry points/challenges.
- Constrain legacy privileges.
- Track and phase out Basic gradually.
- Separate CSRF/session/credential handling.
- Reduce the chance of filter-order bugs becoming vulnerabilities.

If a business contract forces a single URL, write a **custom authentication policy** with full tests and an explicit list of allowed credential types.

### 17.3. Using `authenticated()` Is Often Too Broad

In a mixed chain:

```java
.requestMatchers("/api/orders/**").authenticated()
```

lets **any Authentication marked authenticated** satisfy the rule, without checking credential origin or privileges.

If the contract requires a Bearer JWT and scope, enforce a tighter policy. Illustrative `AuthorizationManager` example:

```java
package com.example.shop;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class ApiAuthorizationPolicies {

    public static AuthorizationManager<RequestAuthorizationContext>
    jwtOrdersReader() {

        return (authenticationSupplier, requestContext) -> {
            Authentication auth = authenticationSupplier.get();

            boolean jwtAccepted =
                auth instanceof JwtAuthenticationToken
                    && auth.isAuthenticated();

            boolean hasScope = jwtAccepted
                && auth.getAuthorities().stream().anyMatch(
                    authority -> "SCOPE_orders.read".equals(
                        authority.getAuthority()));

            return new AuthorizationDecision(
                jwtAccepted && hasScope);
        };
    }
}
```

Attach it to a matcher:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .access(ApiAuthorizationPolicies.jwtOrdersReader())
```

**Limitations of this example:** This policy **accepts only JWT Authentication** and still relies on the decoder verifying issuer/audience/signature. If the API uses opaque tokens, the Authentication type differs and the policy must match. `AuthorizationManager` also **does not replace rejecting conflicting credentials** prior to authentication.

When using a Bearer-only chain as in section 9, checking `JwtAuthenticationToken` explicitly in every rule is usually unnecessary; `hasAuthority("SCOPE_...")` and separated filter mechanisms express the contract cleanly.

### 17.4. If Supporting "Basic or Bearer", Differentiate Authorization by Scheme

An example business policy might be:

```text
Bearer JWT:
  GET orders → requires SCOPE_orders.read
  POST orders → requires SCOPE_orders.write

HTTP Basic:
  GET internal order summary → requires ROLE_LEGACY_READER
  POST/DELETE → never allowed

Web session:
  Not accepted in either API branch
```

Encode this policy in filters/authorization managers and test every combination. Never do:

```text
if authenticated:
    allow all order operations
```

Even when multiple schemes are supported, **no credential may expand the privileges of another credential** unless the protocol requires a combined mechanism and it is explicitly designed.

### 17.5. Requiring Both Differs from "Either One"

A high-risk endpoint may require **mTLS client certificate + Bearer access token** together. These are **two additive proofs**, not a fallback: missing either one must be denied.

That model must verify TLS client identity, token sender-binding if used, audience/scopes, and the relationship between certificate/client/token. Simply enabling `x509()` alongside `oauth2ResourceServer()` **does not automatically enforce AND across both proofs**; use an explicit policy.

---

## 18. API Keys, mTLS, and Gateway Headers: Other Conflicts

### 18.1. API Keys Alongside Bearer

A gateway may require `X-API-Key` in addition to `Authorization: Bearer`. Clarify:

- Is the API key for **client identification/rate-limiting** or an authentication credential granting permissions on its own?
- Are both key and Bearer mandatory?
- If the key is wrong while Bearer is valid, is the request rejected?
- If Bearer is expired while the key is valid, is the request rejected?
- Must the API key's tenant match the Bearer token's tenant?

An API-key filter creating `Authentication` before the Bearer filter can accidentally satisfy `authenticated()` without requiring a Bearer token.

### 18.2. mTLS and Sender-Constrained Access Tokens

mTLS client authentication can authenticate a device/service. When a token is a **certificate-bound access token**, the Resource Server must also match the token's binding (e.g., certificate thumbprint claim per profile) against the actual verified certificate.

Do not assume presenting any client certificate suffices to use a Bearer token issued for a different certificate.

### 18.3. Reverse Proxies Attaching User Headers

For example, after authenticating a user, a gateway might forward:

```http
X-Authenticated-User: alice
X-Authenticated-Tenant: alpha
```

If the backend reads these headers and creates Authentication without guaranteeing requests **arrive only from the trusted gateway**, a client can send:

```http
X-Authenticated-User: admin
```

to impersonate another user.

Ensure:

- No direct access path to the backend bypassing the gateway.
- The gateway strips/overwrites client-sent headers before adding identity headers.
- Gateway–backend connections are secured, with authentication where needed.
- The backend verifies the gateway/source signal per policy.
- Headers carry authority only in **endpoint zones** designed for gateway authentication.

Never let gateway headers become a fallback for Bearer APIs when a token fails.

### 18.4. A Client ID Does Not Replace Audience

Even if a token contains `client_id=legacy-client`, that does not make it a token for `orders-api` or a web session user. Check issuer/audience/scope/client policies independently.

---

## 19. CORS Preflight and "Tokenless" Browser Requests

### 19.1. Preflights Do Not Necessarily Carry Bearer Tokens

A cross-origin SPA sends:

```http
OPTIONS /api/orders/42 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

This is a **CORS preflight**, typically without a Bearer token. If the security chain demands Authentication before CORS runs, browsers fail with CORS errors even when the actual GET request's token is valid.

### 19.2. Dedicated CORS Configuration for the API

In the API chain:

```java
.cors(Customizer.withDefaults())
```

and a matching `CorsConfigurationSource`:

```java
@Bean
CorsConfigurationSource apiCorsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();

    config.setAllowedOrigins(
        List.of("https://app.example.com"));
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE"));
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type"));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();

    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

This example needs imports for `java.util.List` and Spring Web CORS classes. This is a Bearer-header API model **requiring no cross-origin cookies**. If allowing credentials/cookies over CORS, configure exact origins and assess CSRF/cookie policies; never use wildcards carelessly.

### 19.3. Do Not Fix CORS by Dropping Authentication

Wrong:

```java
.requestMatchers("/api/**").permitAll()
```

just to make OPTIONS work. This can expose GET/POST business APIs publicly.

Distinguish preflight from real requests; real requests must still send Bearer tokens and hold proper scopes.

### 19.4. Web Cookies May Be Sent by Browsers to Same-Origin APIs

When a frontend is served from `shop.example.com` and calls `/api/**` on the same origin, browsers may attach `JSESSIONID` automatically. That does not mean the API request is using session authentication.

**Verify with an integration test sending cookie-only requests to the API**; a unit test inspecting only the `Authorization` header will not prove the session boundary.

---

## 20. Reverse Proxies, Load Balancers, and Header Rewriting

### 20.1. Gateway Strips the Authorization Header

Client sends:

```http
Authorization: Bearer <valid-access-token>
```

yet the reverse proxy strips the header when forwarding. The backend sees only the Cookie or no credential at all. The API returns `401`, while the client insists "I sent the token".

Correlate logs showing **header presence/scheme**, request IDs, and gateway hops—without logging actual token values.

### 20.2. Gateway Sends Basic to Authenticate to Upstream

Some setups use HTTP Basic between proxy and backend while frontend clients use Bearer. If the gateway **replaces** `Authorization: Bearer ...` with `Authorization: Basic ...` to authenticate itself to the backend, the Resource Server Bearer filter no longer has the user's token to verify.

This is an architectural issue: two credentials cannot simply share one `Authorization` header. Use a separate upstream authentication mechanism and a token-forwarding/identity-assertion design with a clear trust boundary.

### 20.3. URL Rewrites Can Select the Wrong Chain

Public URL:

```text
https://shop.example.com/api/orders/42
```

yet the proxy rewrites it to:

```text
/orders/42
```

before reaching Spring Boot. `securityMatcher("/api/**")` may fail to match, sending the request to the web catch-all and returning a login redirect or deny.

Verify the exact request path **received by the Servlet application**, context path, and matchers; do not make the API chain match everything and hijack browser endpoints.

### 20.4. Ingress and Backend Must Agree on Duplicate Authorization Handling

If one hop picks the first header and another picks the last, an attacker can craft requests where the proxy validates credential A while the backend accepts credential B.

A sound policy is **rejecting duplicate/invalid headers at ingress**, normalizing headers before forwarding, and running integration tests through the actual gateway/proxy stack.

---

## 21. Login, Logout, Session Fixation, and Credential Lifecycles

### 21.1. Web Sessions Have Their Own Lifecycle

Web login typically:

1. Receives form/OIDC credentials.
2. Creates a browser user Authentication.
3. Applies session fixation protection.
4. Stores SecurityContext per web chain policy.
5. Browser uses the session cookie on subsequent requests.

Cookies should set `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`, and timeouts per deployment. Never put session IDs in URLs or logs.

### 21.2. Basic Credentials Have a Different Lifecycle

HTTP Basic uses username/password/service secrets. Browsers can cache them, and web logout does not automatically invalidate them.

Enforce password rotation, service-account deactivation, rate limiting, auditing, and network restrictions. Use HTTPS because Base64 does not encrypt credentials.

### 21.3. Bearer Tokens Also Have a Different Lifecycle

JWT access tokens have `exp`, issuer/audience, and possibly a revocation strategy. Opaque tokens can be checked as `active` by the AS during introspection.

A token may remain valid after web logout until expiry or revocation per contract. Never treat web session logout as proof a Bearer JWT was revoked.

### 21.4. "Logout Across All Mechanisms" Must Be Designed Explicitly

If the product wants global logout:

- Invalidate the local web session.
- End the OIDC/IdP session via supported protocols where appropriate.
- Revoke refresh/access tokens when supported by AS/Client.
- Disable legacy Basic/service credentials only when specifically requested—never auto-reset system-wide passwords.
- Clear BFF authorized client state/token caches per policy.
- Monitor active sessions/tokens across other services.

Do not create a `/logout` endpoint in the web chain and assume it automatically invalidates every API token.

---

## 22. Testing HTTP with curl: Observing the Right Challenges and Redirects

Suppose Spring Boot runs at `http://localhost:8080` in a lab. Real deployments must use HTTPS.

### 22.1. Protected API Without Token

```bash
curl -i 'http://localhost:8080/api/orders/42'
```

Expect `401` with `WWW-Authenticate: Bearer`.

### 22.2. API with Basic Only

```bash
curl -i -u 'legacy-reader:demo-legacy-password' \
  'http://localhost:8080/api/orders/42'
```

Because the API chain disables HTTP Basic, the request is not treated as a valid Bearer token. Protected APIs normally return `401 Bearer`.

**Never run commands with real passwords into shell history/logs**. These are demo credentials.

### 22.3. Legacy Endpoint Missing Basic

```bash
curl -i 'http://localhost:8080/internal/legacy/status'
```

Expect `401` with a `Basic` challenge.

### 22.4. Legacy Endpoint with Valid Basic

```bash
curl -i -u 'legacy-reader:demo-legacy-password' \
  'http://localhost:8080/internal/legacy/status'
```

If the Controller exists and handles it, may return `200 OK`. Without a Controller, security passes and the endpoint returns `404`.

### 22.5. Legacy Endpoint with Bearer Only

```bash
curl -i -H "Authorization: Bearer $VALID_API_TOKEN" \
  'http://localhost:8080/internal/legacy/status'
```

Bearer does not replace Basic on the legacy chain; protected endpoints normally return `401 Basic`.

### 22.6. Unauthenticated Web Dashboard

```bash
curl -i 'http://localhost:8080/web/dashboard'
```

May receive `302 Location: /login`. Omit `curl -L` when inspecting the initial redirect.

### 22.7. API with Web Cookie and No Bearer

```bash
curl -i \
  -H 'Cookie: JSESSIONID=demo-browser-session' \
  'http://localhost:8080/api/orders/42'
```

Per the Bearer-only API chain, typically still returns `401`. This fake cookie is not a valid web session; real integration tests should use a session cookie **created via login** to prove the session boundary.

### 22.8. API with Valid Bearer Token

```bash
curl -i \
  -H "Authorization: Bearer $VALID_API_TOKEN" \
  'http://localhost:8080/api/orders/42'
```

If the token has valid signature/issuer/audience and `orders.read`, the request passes authentication and endpoint authorization, yet still needs permission for order `42`.

### 22.9. API with Expired Bearer Token + Cookie

```bash
curl -i \
  -H "Authorization: Bearer $EXPIRED_API_TOKEN" \
  -H 'Cookie: JSESSIONID=demo-browser-session' \
  'http://localhost:8080/api/orders/42'
```

Must be rejected by Bearer token validation. Never fall back to the cookie.

### 22.10. Be Careful with Verbose Debugging

`curl -v` can print Authorization headers containing real tokens; `curl -u` can save credentials in command history. When sharing test output, **keep only status codes, filtered headers, and correlation IDs**, never raw tokens or secrets.

---

## 23. Integration Testing with MockMvc: Testing Boundaries, Not Just Scopes

### 23.1. Why Test Through the Real Filter Chain?

A Service test returning 200 does not prove requests enter the right chain. Verify:

- Actual URL matchers.
- Bearer API does not use web sessions.
- Legacy Basic does not use Bearer.
- Unauthenticated web requests redirect.
- Invalid credentials are rejected with no fallback.
- Web CSRF remains active.
- Valid Bearer with authority still enforces business authorization.

### 23.2. MockMvc Example for Status and Challenges

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class CredentialIsolationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiWithoutBearerReturns401() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate",
                org.hamcrest.Matchers.containsString("Bearer")));
    }

    @Test
    void apiDoesNotAcceptLegacyBasic() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(httpBasic(
                    "legacy-reader",
                    "demo-legacy-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void legacyRouteRequiresBasic() throws Exception {
        mvc.perform(get("/internal/legacy/status"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate",
                org.hamcrest.Matchers.containsString("Basic")));
    }

    @Test
    void websiteRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

To make this test pass, you need:

- The `SecurityFilterChain` beans from section 9.
- A matching `UserDetailsService`.
- Handlers if testing successful authorized requests.
- A `JwtDecoder`/test JWKS or mock when the app initializes issuer metadata in the test environment.

This tests response semantics, not yet proving JWT signature/audience validators work.

### 23.3. Real Web Session Tests Must Not Be Replaced by `with(user())`

Spring Security Test's `with(user())` synthesizes a mock Authentication on the request. It **does not represent** a logged-in browser sending a real `JSESSIONID` across another chain.

Session-boundary tests should:

1. Execute `POST /login` with test user and CSRF token.
2. Extract `MockHttpSession` from the login result.
3. Call `GET /web/dashboard` with that session → permitted.
4. Call `GET /api/orders/42` **with only that same session**, no Bearer → `401`.
5. Call the API with a valid JWT and right scope → permitted per API policy.

Skeleton example:

```java
import org.springframework.mock.web.MockHttpSession;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;

MockHttpSession session =
    (MockHttpSession) mvc.perform(
            post("/login")
                .with(csrf())
                .param("username", "web-user")
                .param("password", "demo-web-password"))
        .andExpect(status().is3xxRedirection())
        .andReturn()
        .getRequest()
        .getSession(false);

mvc.perform(get("/web/dashboard").session(session))
    .andExpect(status().isOk());

mvc.perform(get("/api/orders/42").session(session))
    .andExpect(status().isUnauthorized());
```

This is an **integration test skeleton**; adjust session creation/login success behavior for your app and add a `/web/dashboard` Controller. Never log real session IDs.

### 23.4. Testing JWT Authorities Does Not Replace Decoder Tests

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

mvc.perform(get("/api/orders/42")
        .with(jwt()
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.read"))))
    .andExpect(status().isOk());
```

`with(jwt())` typically creates a mock `JwtAuthenticationToken` and **does not verify signature/JWKS/issuer/audience**. It suits testing authorization rules, not proving real Bearer tokens validate properly.

Add tests with JWTs signed by a test private key, a stub JWKS, and the real decoder to verify audience/issuer/expiry and `invalid_token` errors.

### 23.5. Actively Testing Credential Conflicts

If policy defines **reject duplicate Authorization headers**, test through real ingress/containers or production-like mocks so header normalization does not disagree across hops.

Test:

- Two Authorization headers with the same scheme.
- One Basic header and one Bearer header.
- An Authorization header with unusual commas or whitespace.
- Broken Bearer token alongside a logged-in session cookie.
- Wrong-password Basic alongside a logged-in session cookie.
- Gateway attaching an identity header when the client also sends that header.
- Headers arriving with different casing/normalization, even though HTTP header names are case-insensitive.

Test every layer **reverse proxy → Servlet container → Spring Security**, not just unit-testing a resolver.

---

## 24. Testing CSRF, Basic, and Other Mechanisms

### 24.1. Web POST Missing CSRF

With an endpoint `POST /web/profile` and a logged-in user:

```java
mvc.perform(post("/web/profile")
        .session(authenticatedWebSession)
        .param("displayName", "Alice"))
    .andExpect(status().isForbidden());
```

When CSRF is enabled, this is the expected outcome. Tests with `with(csrf())` should pass CSRF, while still requiring handler/business permissions.

### 24.2. Do Not Use Basic for All REST Writes Just to Avoid Token Management

If legacy clients must write data, allowing HTTP Basic across `/api/**` creates long-lived credentials sent on many requests with hard-to-restrict audience/scopes. Plan a migration to OAuth Client Credentials or mTLS/sender-constrained tokens per architecture.

### 24.3. Testing 401/403 Does Not Replace Object-Level Permission Tests

A valid Bearer token with `SCOPE_orders.read` belonging to tenant Alpha must not read Beta's orders. Test Services/Repositories with tenant and owner predicates, not only `hasAuthority`.

### 24.4. "No Fallback" Tests Are Mandatory

Especially critical cases:

```text
valid_web_cookie + invalid_bearer
  → API must reject

valid_web_cookie + missing_bearer
  → API must reject

valid_basic + missing_bearer
  → API must reject

valid_bearer + missing_basic
  → legacy Basic endpoint must reject

valid_bearer + insufficient_scope
  → API must reject with authorization failure
```

If any case above unexpectedly succeeds, investigate chain selection, `SecurityContextRepository`, or custom fallbacks.

---

## 25. Categorized Error Handling and Observability

### 25.1. Never Log Raw Credentials

Never log:

```text
Authorization: Bearer <real-token>
Authorization: Basic <encoded-real-password>
Cookie: JSESSIONID=<real-session>
X-API-Key: <real-key>
introspection client_secret=<secret>
```

Those values are credentials that can be stolen from logs, traces, or support tickets.

### 25.2. Data to Record Under Control

| Field | Meaning |
|---|---|
| Correlation/request ID | Traces requests across hops |
| Route pattern | Identifies whether URL entered API, legacy, or web |
| SecurityFilterChain ID/group | Identifies which chain actually ran |
| Observed credential scheme | Bearer, Basic, cookie-only, or none—**never credential values** |
| Authentication result category | Missing/malformed/invalid/authenticated |
| Principal type | JWT, opaque, form, Basic, custom |
| Authority policy result | Whether scope/role passed |
| Tenant authorization result | Access within or outside rights |
| HTTP status and challenge type | `401 Bearer`, `401 Basic`, `302 login`, `403` |
| IdP/JWKS/introspection availability | Distinguishes bad tokens from infrastructure errors |
| Config revision | During migrations/chain policy updates |
| Gateway forwarding result | Were headers stripped/rewritten? |

Control PII and cardinality; never put raw tokens, user emails, or session IDs into metric labels.

### 25.3. Spring Security Logging in Development

Example:

```yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: TRACE
    org.springframework.security: DEBUG
```

This level is useful when pinpointing selected chains/filters, but enable it boundedly and avoid exposing sensitive details in production logs.

### 25.4. Distinguishing Failure Types

**API returns 302 to `/login`:** likely hit the web chain by mistake or entry point configured for browsers.

**API returns 401 Basic:** Basic entry point may be applying unintentionally.

**API with `JSESSIONID` and no token still returns 200:** check whether SecurityContext is read from session or a custom fallback exists.

**API with invalid Bearer token still returns 200:** especially dangerous; check whether the decoder actually ran, caching/authentication state, and credential filtering.

**Legacy Basic with right password returns 403:** user may lack `ROLE_LEGACY_READER`, or CSRF/another authorization check rejected it.

**Web POST with valid cookie returns 403:** likely CSRF protection working as intended—do not rush to disable it.

**Browser reports CORS error:** preflight may not be handled properly; inspect CORS before assuming the JWT is broken.

---

## 26. Risk and Solution Matrix

| Mistake | Risk / behavior | Solution |
|---|---|---|
| One mixed chain for both web and API | Session can satisfy `authenticated()` at the API | Split chains + stateless API |
| API missing `securityMatcher` | API chain hijacks the whole website | Explicit matchers and catch-all last |
| Web catch-all has `@Order(1)` | API gets login redirects | Order API chain before web |
| `anyRequest().authenticated()` on mixed chain | All credentials treated as equivalent | Policies per scheme, scope, and route |
| Invalid Bearer → session fallback | Expired/revoked tokens still gain access | Fail closed, Bearer-only API |
| Invalid Basic → session fallback | Basic policy bypassed | Separate Basic chain, no fallback |
| Web role used as OAuth scope | Web permissions leak API access | Verify access tokens and scopes |
| Basic and Bearer in one header | Ambiguous/invalid syntax | One scheme per Authorization credential |
| Multiple Authorization headers | Proxy/backend disagreement | Reject/normalize at ingress |
| Disabling CSRF application-wide | Browser session/Basic exposed to CSRF | Keep web CSRF; disable only on Bearer-only APIs |
| Bearer stored in cookie yet treated CSRF-exempt | Ambient credential exploited | Threat-model by how credential is sent |
| API reads session from HttpSession | Violates OAuth boundary | `NullSecurityContextRepository`/`STATELESS` + no custom fallback |
| Form login URL outside web chain | `/login` broken or unprotected | Web catch-all or covering matcher |
| OIDC callback outside web chain | Login flow fails | Ensure callbacks enter `oauth2Login` chain |
| Gateway strips Bearer header | Confusing API 401s | Verify forwarding policy |
| Gateway replaces Bearer with Basic | Loses user token/protocol | Dedicated upstream credential design |
| Trusting self-asserted `X-Authenticated-User` | User impersonation | Gateway trust boundary, strip incoming headers |
| Checking only JWT issuer | Tokens from another API accepted | Audience validator |
| Checking only JWT scope | BOLA/cross-tenant | Repository/Service tenant-owner ACL |
| Using OIDC ID token on API | Token confusion | Require access token with right audience |
| Not distinguishing 401/403/302 | Broken client handling, hard debugging | Per-chain entry points |
| Overly broad Authentication cache | Stale permission decisions | Policy-driven lifecycle and invalidation |
| `with(jwt())` tests pass | Misses decoder bugs | Signed JWT integration tests |
| Treating web logout as JWT revocation | Unexpired tokens still work | Separate token lifecycle/revocation |

---

## 27. Design Checklist for a Multi-Mechanism System

Before implementing, answer all of the following groups of questions thoroughly.

### 27.1. Protection Zones

- Which URLs belong to browsers, APIs, service accounts, and admins?
- Do any endpoints genuinely need to accept multiple schemes at once?
- Is there a catch-all security chain at the end?
- Do any path rewrites/gateway rules prevent matchers from matching?
- Which chain owns `/login`, `/logout`, and OIDC authorization/callback endpoints?

### 27.2. Credentials and State

- Does the API accept only Bearer headers?
- Are sessions loaded/saved in the API chain?
- Can Basic users call the API, or only legacy routes?
- If a request has both a cookie and Bearer, which credential is trusted?
- If Bearer is invalid, is there any fallback? The default should be **no**.
- If tokens are stored in cookies, is CSRF policy still sound?
- Can two Authorization headers be handled differently by proxy vs. backend?

### 27.3. Tokens and Permissions

- Which decoder/introspector verifies JWT/opaque tokens?
- Where are issuer, JWKS, algorithm, audience, and token profile defined?
- Do scopes/authorities use the proper `SCOPE_` prefix?
- Can principals from Basic/session accidentally hold authorities used by Bearer policies?
- Are tenant/owner/ACLs enforced in Services/Repositories?

### 27.4. Browser Protection

- Do web session cookies set `Secure`, `HttpOnly`, `SameSite`, and proper timeouts?
- Does form/OIDC login have CSRF/correlation state?
- Do POST/PUT/DELETE endpoints relying on cookies or Basic in browsers have CSRF protection?
- Does web logout invalidate the session?
- Does web login include session fixation protection?

### 27.5. Testing and Operations

- Have cookie-only API requests been tested to return 401?
- Have expired Bearer + valid cookie requests been tested to reject?
- Have Basic-only calls to the Bearer API been tested to reject?
- Have Bearer-only calls to legacy Basic been tested to reject?
- Have Basic + Bearer in the same request or duplicate headers been tested?
- Have web redirects, API challenges, CSRF, and CORS been tested?
- Have tests run through the real reverse proxy?
- Do logs avoid leaking credentials?
- Is there a Basic deprecation plan and migration metrics?

---

## 28. Self-Check Questions

**Q1.** A website is already logged in with `JSESSIONID`. Does that permit calling a Bearer-only API without sending an access token?

**Answer:** No. The API chain must validate the Bearer token per contract; web cookies do not replace access tokens.

**Q2.** An API request carries an expired Bearer token and a valid web session. Should the session be tried if JWT verification fails?

**Answer:** No in a Bearer-only model. That is credential fallback bypassing expiration/audience/token policies; the request must be rejected.

**Q3.** Does Spring Security run every `SecurityFilterChain` and merge their results?

**Answer:** No. `FilterChainProxy` selects the first matching chain; later chains are not applied to that request.

**Q4.** How does `securityMatcher` differ from `requestMatchers`?

**Answer:** `securityMatcher` selects the entire chain; `requestMatchers` defines authorization rules inside the selected chain.

**Q5.** When enabling `formLogin`, `httpBasic`, and `oauth2ResourceServer` in the same chain, is the API guaranteed to accept only Bearer?

**Answer:** No. If the chain reads sessions and rules only check `authenticated()`, another Authentication type can satisfy the rule. Separate chains or constrain mechanisms via explicit policies.

**Q6.** Why isn't HTTP Basic automatically exempt from CSRF?

**Answer:** Browsers can cache and auto-send Basic credentials within the protection space, allowing external sites to trigger authenticated requests under certain conditions. Evaluate ambient credentials and state-changing operations.

**Q7.** If a Bearer token is placed in a cookie, is the API still CSRF-exempt just because the token is called Bearer?

**Answer:** No. When browsers auto-send cookies carrying credentials, the threat model changes; evaluate CSRF like any cookie-based mechanism.

**Q8.** Is HTTP Basic using Base64 safe over plain HTTP?

**Answer:** No. Base64 is encoding, not encryption. HTTPS is required, and protect username/password as secrets.

**Q9.** A client sends two Authorization headers, one Basic and one Bearer. What should the server do?

**Answer:** Have a consistent reject/normalize policy at ingress and backend; never assume every hop picks the same header or merges two supported schemes.

**Q10.** Should an API without a token redirect to `/login` or return `401 Bearer`?

**Answer:** Per the Resource Server API contract, typically `401` with `WWW-Authenticate: Bearer`. Redirects fit browser web login.

**Q11.** Can a token with `SCOPE_orders.read` and `aud=billing-api` call `orders-api`?

**Answer:** No if the API requires audience `orders-api`. Scopes do not replace audience.

**Q12.** Does a user with `ROLE_WEB_ADMIN` in a session implicitly possess `SCOPE_orders.write`?

**Answer:** No. Web roles and OAuth access token scopes are different permission sources; never translate privileges automatically without an explicit policy.

**Q13.** Does `SessionCreationPolicy.STATELESS` stop browsers from sending `JSESSIONID`?

**Answer:** No. Cookies may still be sent, yet the API chain should not use that session as SecurityContext authentication.

**Q14.** After web logout, does a previously issued Bearer JWT automatically become invalid?

**Answer:** Not by default. It still depends on `exp`, revocation, and AS/Resource Server policy, separate from the web session.

**Q15.** Does a test using `with(jwt())` returning 200 prove real JWT token signatures are verified properly?

**Answer:** No. That test typically mocks Authentication; integration tests with a decoder/JWKS and real signed tokens are needed to check signature/issuer/audience.

**Q16.** If both an API key and Bearer must be used together, is simply enabling two filters enough to require both?

**Answer:** No. You need explicit "AND" or "OR" rules, ordering/precedence, client-to-token binding, error handling, and authorization—never depend on accidental filter order.

**Q17.** Does a CORS preflight without a Bearer token prove the API allows anonymous GET/POST access?

**Answer:** No. Preflight checks only browser CORS policy; real requests still require valid credentials and scopes.

**Q18.** Can a gateway swap a Bearer header for a Basic header to authenticate itself to the backend while the Resource Server still reads Bearer from that same header?

**Answer:** No. Design upstream identity/credential forwarding separately; a single `Authorization` header cannot carry two separate valid credentials simultaneously.

---

## 29. References

Official sources to cross-check with **the Spring Security version used by your project**:

- [Spring Security Reference — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `Authentication`, `AuthenticationManager`, providers.
- [Spring Security Reference — Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances): multiple `SecurityFilterChain` beans and matchers.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): Bearer JWT, decoder, authority mapping.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and principals.
- [Spring Security Reference — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): browser credentials, CSRF policy.
- [Spring Security Reference — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): security context and HTTP sessions.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OIDC/browser login.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer transport, `WWW-Authenticate`, and errors.
- [RFC 7617 — The 'Basic' HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): HTTP Basic.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): `Authorization` and `WWW-Authenticate`.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, OIDC client, and authentication flow.

For APIs like `SecurityFilterChain`, `SessionCreationPolicy`, `JwtDecoder`, and `oauth2ResourceServer`, always consult **the exact version's Javadoc**. The snippets here illustrate modern Servlet Spring Security architecture and must be adapted to your real application configuration.

---

## 30. Key Takeaways

In an application combining **session cookies, HTTP Basic, OAuth Bearer, and other authentication mechanisms**, bugs rarely come from a credential "not existing", but rather from **a credential valid in context A being accepted in context B**.

Essential rules:

1. **Separate resource zones by authentication mechanism** using `securityMatcher`, `@Order`, and multiple `SecurityFilterChain` beans when appropriate: Bearer API, legacy Basic, browser session.
2. **Never fall back when a presented credential fails**: invalid Bearer must not be rescued by cookies or Basic; invalid Basic must not be rescued by web sessions.
3. **Never treat all `Authentication` objects as equivalent**: `authenticated()` alone can be overly broad; APIs need the right token contract, scope, audience, tenant, and business ACLs.
4. **Apply CSRF per actual credential model**: browser session cookies/Basic differ from pure Bearer-header APIs; never disable CSRF application-wide.
5. **Resolve duplicate/header ambiguity at trust boundaries**: never merge Basic and Bearer, never trust client-sent identity headers, and verify proxy forwarding.
6. **Respond appropriately per surface**: APIs use `401/403` Bearer, legacy uses Basic challenges, websites use login redirects/sessions.
7. **Test credential combinations**: cookie-only API, expired Bearer + valid cookie, Basic-only API, Bearer-only legacy, CSRF, CORS, logout, and proxy rewrites.

**Good design is not "the more ways to log in, the better"—it is ensuring each request accepts only credentials allowed by that resource's contract, and no mechanism silently bypasses another.**
