# Request Cache, Redirects, and Behaviors Unsuitable for Machine-Called APIs

## 1. The problem: web login mechanisms do not always fit a Resource Server

A Spring Security application can serve **interactive user web pages** or **machine-called APIs**. These two client types have very different authentication experiences:

- A **browser web app** can send users to a login page, retain the original URL in a session, and return users after login.
- **Machine-to-machine APIs**, mobile apps, CLIs, batch jobs, service meshes, or other backends normally do not have a user waiting to enter a password. They send an **OAuth 2.0 access token** via `Authorization: Bearer ...` and expect an HTTP response with protocol-appropriate status, headers, and body.

In the **Spring Security OAuth 2.0 OIDC Resource Server** module, **Web Security and State** chapter, this lesson focuses on the question: **When configuring a Bearer token API, how must request cache, redirects, and browser-login features be handled so they do not break the API contract?**

An unwanted scenario:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Accept: application/json
~~~

A Resource Server lacking separation between API and browser configs results in:

~~~http
HTTP/1.1 302 Found
Location: /login
Set-Cookie: JSESSIONID=<SESSION_ID>
~~~

An HTTP client automatically follows the redirect and receives:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html

<!doctype html>
<html><body><form action="/login" method="post">...</form></body></html>
~~~

**The API never actually returned order data.** Yet the client might see HTTP 200 after the redirect, try parsing HTML as JSON, or mistakenly record that the call succeeded. Beyond protocol issues, sessions and request caches can create unnecessary server-side state.

For a **Bearer-token-only Resource Server**, the typical response when a token is missing is:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Cache-Control: no-store
~~~

There is no login page, no redirect to an Identity Provider, and no need to save URLs for post-login restoration. With a valid token lacking permissions, the response is typically **403 Forbidden**.

> Lesson scope: **Resource Server APIs**. Browser-facing OAuth 2.0 Authorization Code/OIDC login **does rightly use protocol redirects**. Not every redirect is bad; the mistake is applying a browser-login workflow to an API serving machine clients.

## 2. What is a request cache?

In Spring Security Servlet, **`RequestCache`** is the abstraction that retains an initial request so it can be restored or navigated back to after the user authenticates. This mechanism is usually paired with web apps using **form login** or interactive OAuth 2.0 login.

Typical browser flow:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Spring Security
    participant W as Login page / Identity Provider
    B->>S: GET /account/profile (not logged in)
    S->>S: Save request via RequestCache
    S-->>B: 302 Location: /login
    B->>W: Render/visit login page
    W-->>S: Login succeeds per flow
    S->>S: Retrieve saved request
    S-->>B: Redirect to /account/profile
    B->>S: GET /account/profile (logged in)
    S-->>B: Return content
~~~

This mechanism is helpful when a browser has a human user and **session state** supporting the workflow. However, an API client expecting JSON cannot "log in and come back" in the same way; saving the request and returning 302 only causes errors.

### 2.1. Common Servlet components

| Component | Role |
|---|---|
| `RequestCache` | Contract for saving and retrieving requests that required authentication |
| `HttpSessionRequestCache` | Implementation saving the `SavedRequest` into the HTTP session |
| `SavedRequest` / `DefaultSavedRequest` | Representation of the saved request's metadata |
| `NullRequestCache` | Implementation that saves nothing; suitable for stateless APIs |
| `RequestCacheAwareFilter` | Helps restore a saved request when needed |
| `ExceptionTranslationFilter` | Connects authentication/authorization exceptions to entry points and request cache |
| `AuthenticationEntryPoint` | Determines how to respond when authentication is required |
| `LoginUrlAuthenticationEntryPoint` | Browser-oriented entry point, typically redirecting to a login URL |
| `SavedRequestAwareAuthenticationSuccessHandler` | Uses saved requests to redirect after browser login |
| `BearerTokenAuthenticationEntryPoint` | Returns an RFC 6750 Bearer challenge when authentication fails |
| `BearerTokenAccessDeniedHandler` | Returns a response when a Bearer-authenticated principal lacks permissions |

None of these components verify JWT signatures or introspect tokens. Those steps belong to **`JwtDecoder`** or **`OpaqueTokenIntrospector`**. Request cache is **HTTP/navigation workflow**, not an access token store or authorization mechanism.

### 2.2. What information does RequestCache store?

With `HttpSessionRequestCache`, a saved request may store URL, method, and request metadata needed to restore navigation. Exact details depend on the framework and configuration.

**Never treat a saved request as a store for business payloads**, never write Bearer tokens/Authorization headers into it, and never rely on request cache to arbitrarily replay a state-changing POST. A fresh browser redirect typically creates a new HTTP request; that is different from guaranteeing every piece of the old request is safely replayed.

For APIs carrying sensitive data in URL query strings, storing URLs unnecessarily in a session also expands data exposure. Avoid putting access tokens in query strings in the first place, and for pure Bearer APIs, **saved requests are usually unnecessary**.

### 2.3. Is RequestCache an HTTP response cache?

**No.** These are three distinct concepts:

| Name | What does it store? | Purpose |
|---|---|---|
| **Spring Security RequestCache** | Unauthenticated request to resume a browser flow | Post-login redirection |
| **HTTP response cache** | HTTP response representation per `Cache-Control`/ETag | Browser, CDN, and proxy performance |
| **Token/introspection cache** | Verified access token results or JWKS/state | Reducing authentication check overhead |

`NullRequestCache` **does not disable HTTP caching**, does not clear JWT caches, and does not shield responses from CDNs. Conversely, a response's `Cache-Control: no-store` **does not replace** disabling saved requests.

## 3. What happens when a request is unauthenticated?

To understand where redirects originate, distinguish the processing branches in Spring Security:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Selected SecurityFilterChain"]
    B --> C{"Bearer token present?"}
    C -->|Yes| D["BearerTokenAuthenticationFilter"]
    D --> E{"Token verified?"}
    E -->|No| F["Bearer authentication failure / entry point"]
    E -->|Yes| G["Authenticated Authentication"]
    C -->|No| H["Anonymous or unauthenticated"]
    H --> I["HTTP authorization"]
    G --> I
    I --> J{"Rule satisfied?"}
    J -->|Yes| K["Controller / service"]
    J -->|"No, unauthenticated"| L["Exception translation / authentication entry point"]
    J -->|"No, authenticated"| M["AccessDeniedHandler"]
    F --> N["Typically 401 + WWW-Authenticate: Bearer"]
    L --> O["401 Bearer or 302 login depending on chain/entry point"]
    M --> P["Typically 403"]
~~~

Note: **Not all errors are emitted from the same filter.** `BearerTokenAuthenticationFilter` can handle token validation errors directly through its own entry point. `ExceptionTranslationFilter` primarily handles `AuthenticationException` and `AccessDeniedException` thrown by downstream filters. This distinction matters when writing custom handlers and seeing a handler not get invoked as expected.

### 3.1. Browser entry points and API entry points differ

Consider the same unauthenticated request `GET /api/orders`:

| Chain configuration | Possible behavior |
|---|---|
| Browser form login + `LoginUrlAuthenticationEntryPoint` | 302 redirect to `/login` |
| Browser OAuth 2.0/OIDC login | Redirect to start the appropriate authorization/login flow |
| HTTP Basic | 401 with `WWW-Authenticate: Basic ...` |
| Bearer Resource Server | 401 with `WWW-Authenticate: Bearer` |
| Misconfigured custom handler | May return 200, HTML, or an off-contract redirect |

Spring Security may pick an entry point via matchers/content negotiation when multiple mechanisms coexist. Therefore, never assume merely adding one `oauth2ResourceServer()` line guarantees **no URL in any chain** will ever redirect to login.

### 3.2. When a request carries an invalid Bearer token

Example:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <EXPIRED_OR_INVALID_TOKEN>
~~~

The Bearer challenge response typically includes:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Do not redirect to form login to "fix" a machine caller's expired token. The API client must manage its credential lifecycle per OAuth 2.0: using valid client-side token acquisition/refresh flows if allowed, or surfacing an error to operators. The Resource Server is not the place to launch interactive logins whenever a token is invalid.

### 3.3. Valid token lacking scope

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <VALID_TOKEN_WITHOUT_ORDERS_READ>
~~~

The typical response is:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Exact behavior/headers depend on `AccessDeniedHandler`, principal state, and authority configuration. **Never turn a missing scope into a login redirect** hoping the user logs in again; granting additional permissions belongs to proper authorization/administration flows, not silently bypassing security policy.

## 4. Why do redirects break machine-called APIs?

### 4.1. Client follows redirects and receives HTML instead of JSON

Many HTTP clients follow `Location` automatically on 301/302/303/307/308 depending on settings. An API client might see:

~~~text
GET /api/orders/42
  → 302 /login
  → GET /login
  → 200 text/html
  → JSON parser error
~~~

Another client **does not follow redirects** and surfaces 302 to the app. Two clients calling the same API exhibit different failures, making incidents hard to diagnose.

### 4.2. Redirects alter request semantics

For POST/PUT/PATCH/DELETE, redirect status codes carry different semantics for methods and bodies. Some clients convert POST to GET on 302/303; 307/308 tend to preserve method/body. Expecting "log in and automatically replay a write request" is unsafe.

For machine API clients, the right design is **returning a clear authentication status directly on the original request**, never relying on redirect navigation.

### 4.3. Redirects can create information-disclosure risks

An improperly designed `Location` can:

- Send clients to an unintended host.
- Leak query parameters or sensitive URLs into login pages or logs.
- Trigger hard-to-control redirect chains.
- Produce inconsistent behavior depending on whether an HTTP client forwards `Authorization` across redirects.

**Never design redirects carrying raw Bearer tokens in query strings.** Even if an HTTP client library strips `Authorization` across host changes, do not rely on that behavior as a primary defense.

### 4.4. Redirects are not a bug in OIDC Authorization Code

A browser-facing **OIDC client** may run:

~~~text
Browser → Client app → Authorization Server login
        → Authorization Code callback
        → Client app processes code + token endpoint
~~~

That is a **purpose-built OAuth 2.0/OIDC flow**, featuring `state`, PKCE/nonce where applicable, and anti-attack checks. It does not mean every Bearer Resource Server API should redirect arbitrary clients to an IdP when a request lacks a token.

**OAuth2 Client/Login** and **OAuth2 Resource Server** are distinct security roles, even when both are supported by Spring Security in one system.

## 5. Designing a Resource Server API without saving requests

Suppose the Orders API has these requirements:

| Endpoint | Requirement |
|---|---|
| `GET /api/orders/**` | Access token has `SCOPE_orders.read` |
| `POST /api/orders` | Access token has `SCOPE_orders.create` |
| `GET /api/me` | Authenticated principal |
| `GET /api/public/status` | Public |
| Unclassified URLs | Denied |

Desired HTTP policy:

1. Never redirect clients to `/login` or an Identity Provider.
2. Never save requests in an HTTP session for post-login redirection.
3. Never use cookies/sessions to persist Bearer authentication across requests.
4. When tokens are missing/invalid, return an appropriate Bearer challenge.
5. When authenticated yet lacking authorities, return an authorization error.
6. Every protected request must be authenticated using that request's own valid token/proof.

### 5.1. Dependencies

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

For JWTs, the Resource Server needs the corresponding JOSE implementation; modern Spring Boot starters usually pull in the appropriate dependency. If managing dependencies manually, check the Spring Security OAuth 2.0 JOSE module for your project version.

### 5.2. Issuer configuration

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

`issuer-uri` is the preconfigured trusted source. The API should also validate `aud` for `orders-api` if the contract requires it; checking issuer and signature alone does not prove the token was meant for this resource audience. If using opaque tokens, the alternative introspection endpoint configuration is shown later.

### 5.3. Servlet `SecurityFilterChain` configuration for a Bearer API

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache())
            )
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .oauth2Login(AbstractHttpConfigurer::disable)
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/status")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

This is an illustrative configuration for a **Bearer-token-only Servlet API** that does not use browser sessions/cookies as credentials. Key decisions:

- `SessionCreationPolicy.STATELESS`: Spring Security does not use HTTP sessions to maintain the security context across requests.
- `NullRequestCache`: does not save requests awaiting authentication for post-login redirection.
- `formLogin(...disable)`, `oauth2Login(...disable)`: does not activate interactive logins in this API chain.
- `httpBasic(...disable)`: does not trigger browser Basic login prompts on the API.
- `csrf(...disable)`: appropriate only under the assumption that the API does not use browser-auto-sent credentials such as cookie-based session authentication. **Never copy this decision to browser apps using cookies.**
- `oauth2ResourceServer(...jwt(...))`: Spring Security processes Bearer JWTs and returns Resource Server authentication responses.
- `anyRequest().denyAll()`: unclassified URLs/methods are not implicitly accepted.

This example omits controllers, audience validators, per-order permissions, or a CORS source if browser JavaScript is one of the API consumers. Those must be configured per the system contract.

**Never write a custom `AuthenticationEntryPoint` returning 302.** Spring Security Resource Server provides a Bearer token entry point; when overriding exception handling, preserve those semantics.

### 5.4. Notes on `csrf(...disable)`

In a pure Bearer API:

~~~text
Client explicitly sends Authorization: Bearer <token>
No session cookie is used as a credential
Does not rely on browser auto-sent cookies for authentication
~~~

CSRF is generally not a risk under the cookie-based browser-auto-attached credential model. However, if the same server also has:

- Cookie-based session authentication.
- Browser-cached and auto-sent HTTP Basic auth.
- Refresh/session cookies on data-mutating endpoints.
- Form-based login or POSTs authenticated via browser cookies.

then **you cannot conclude it is safe merely because "Resource Server is enabled."** CSRF protection is needed on the appropriate chains/endpoints, or chains must be cleanly separated. Disabling CSRF on the API chain must never weaken protection on browser routes.

### 5.5. If you want explicit Bearer entry point policies

You can configure the two Spring Security-provided handlers:

~~~java
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;

http.exceptionHandling(ex -> ex
    .authenticationEntryPoint(new BearerTokenAuthenticationEntryPoint())
    .accessDeniedHandler(new BearerTokenAccessDeniedHandler())
);
~~~

The snippet above is an **additional configuration block** inside the Servlet `HttpSecurity` option, not a second `SecurityFilterChain` bean. `BearerTokenAuthenticationEntryPoint` returns the proper challenge for authentication failures; `BearerTokenAccessDeniedHandler` handles access denied per Bearer semantics.

In applications without custom entry points, the Resource Server config usually already sets up the right Bearer handlers. Only override when harmonizing multiple mechanisms/chains and after verifying entry point registration order.

### 5.6. Does replacing JWT with opaque tokens change the stateless requirement?

No. A Resource Server can use:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()))
~~~

with introspection configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

These properties use environment variables/secret managers appropriately. Authentication then validates tokens via introspection; **request cache and login redirects remain unnecessary** when the API serves only machine clients. Do not confuse an **introspection cache** (reducing token-checking cost) with a **saved request cache** (restoring URLs after browser login).

## 6. `NullRequestCache` and `SessionCreationPolicy.STATELESS` solve two different questions

A common design mistake is thinking one of the two alone makes the system "completely stateless."

| Configuration | What does it control? | What does it NOT guarantee? |
|---|---|---|
| `requestCache(new NullRequestCache())` | Does not save/restore saved requests via `RequestCache` | Does not stop other filters/controllers from creating an HTTP session |
| `sessionCreationPolicy(STATELESS)` | Spring Security does not use HTTP sessions to get/save security context under this policy | Does not forbid app code or libraries from calling `request.getSession()` |
| `formLogin(disable)` | Disables browser form authentication in this chain | Does not disable OAuth2 Login or Basic if enabled elsewhere |
| `oauth2Login(disable)` | Does not start OIDC/OAuth2 browser login in this chain | Does not by itself configure Bearer authentication |
| `NullSecurityContextRepository` | Does not persist security context via that repository | Does not forbid all sessions or replace JWT signature validation |
| `csrf(disable)` | Disables CSRF filter protection within this chain | Not a statelessness mechanism; creates risk if cookie auth remains active |

### 6.1. Why specify both session policy and request cache?

Two independent needs:

~~~text
Authentication continuity across requests:
    SessionCreationPolicy / SecurityContextRepository

Restoring URL after browser login:
    RequestCache / SavedRequest
~~~

An app might not persist authentication in a session yet still have a library creating a session to store an OAuth 2.0 authorization request. Conversely, you might disable request caching while still using session cookies to preserve browser logins. Do not conflate the two cases.

### 6.2. `SecurityContextRepository` and request-scoped context

Spring Security holds `Authentication` in the security context while processing a request. Some repository implementations persist context across HTTP sessions; others use request attributes only or persist nothing across requests.

For a Bearer Resource Server:

~~~text
Request A carries Bearer token A
  → authenticates A
  → uses principal A during request A
  → no session needed for request B to reuse A

Request B carries Bearer token B
  → authenticates B independently
~~~

`SessionCreationPolicy.STATELESS` expresses the intent not to use sessions to link authentication between A and B. It does not mean the security context should "vanish" before services/controllers run **within the same request**; the context is still needed for the request lifecycle.

### 6.3. Should you force `NullSecurityContextRepository`?

Spring Security may use a request-attribute repository to retain context across certain dispatches/error handling, or another repository depending on configuration. To customize persistence explicitly:

~~~java
import org.springframework.security.web.context.NullSecurityContextRepository;

http.securityContext(context -> context
    .securityContextRepository(new NullSecurityContextRepository())
);
~~~

This is an **intentional customization option**, not mandatory for every API already configured with `STATELESS`. When using `NullSecurityContextRepository`, verify behavior on `ERROR`/`ASYNC` dispatches, filters, and exception handling that rely on request-scoped security context. Do not accidentally wipe context needed by valid steps within the same request.

If the goal is simply **not saving saved requests and not maintaining authentication via sessions**, `NullRequestCache` + `STATELESS` with Resource Server is usually the clearer starting point.

### 6.4. Does `JSESSIONID` still appearing prove Spring Security is misconfigured?

You cannot conclude solely from one header:

~~~http
Set-Cookie: JSESSIONID=<SESSION_ID>
~~~

The session may have been created by a controller, view engine, CSRF token repository, OAuth2 Login chain, monitoring library, or another component. Identify **which chain was selected** and which source called `getSession()`. `STATELESS` only sets Spring Security's policy within its scope; it does not disable every session-creating API in the Servlet container.

To verify a pure API:

- Send requests with no prior cookie/session.
- Call endpoints both successfully and unsuccessfully.
- Observe whether the API emits `Set-Cookie: JSESSIONID`.
- Check whether any component genuinely needs to create a session.
- If zero sessions are required, fix that component directly rather than piling on unrelated security flags.

### 6.5. Is saving a token into a session to avoid re-verification appropriate?

A Bearer Resource Server normally must not turn token-authenticated requests into server "login sessions." Accepting a token once and saving `Authentication` in a session to skip checking later requests alters the trust model:

- Clients start relying on cookies/sessions as a new credential.
- Revocation/expiry/audience may no longer be re-evaluated per policy.
- CSRF and session fixation become relevant concerns.
- The API is no longer cleanly stateless Bearer authentication.

If a product requires maintaining browser sessions, design a proper **web login/BFF architecture** with session management, CSRF, cookie flags, refresh, and logout; never create hidden sessions just to "save decoder/introspection calls" on a Bearer API.

## 7. Browser login and Bearer Resource Server can coexist in one application

A product may serve both:

~~~text
/web/**        Browser UI, OAuth2 Login + session cookie
/api/**        Machine API, Bearer JWT/opaque, stateless
/public/**     Public files/pages
~~~

The two groups do not have to share the same `AuthenticationEntryPoint`, `RequestCache`, CSRF policy, or session strategy.

**Separating `SecurityFilterChain`s by URL scope is usually far easier to control** than guessing whether a client is a browser based solely on `Accept: text/html`.

### 7.1. Chain selection order

In Servlet, `FilterChainProxy` iterates through multiple `SecurityFilterChain`s and picks **the first chain matching the request**. `@Order` decides ordering, while `securityMatcher(...)` defines each chain's scope.

~~~mermaid
flowchart TD
    R["HTTP request"] --> P["FilterChainProxy"]
    P --> A{"Matches API chain first?"}
    A -->|Yes| B["/api/**: Bearer + stateless + NullRequestCache"]
    A -->|No| C{"Matches Browser chain?"}
    C -->|Yes| D["/web/**: OAuth2 Login + session + saved request"]
    C -->|No| E["Fallback: default deny / public allowlist"]
    B --> F["API: 401/403 or business data"]
    D --> G["Browser: may redirect to login"]
    E --> H["Response per fallback policy"]
~~~

An `anyRequest().denyAll()` inside the API chain applies only to requests **that matched `securityMatcher("/api/**")`**. It does not protect URLs that match no chain at all. Always include a fallback chain or equivalent protection.

### 7.2. Example of two chains with different policies

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class MixedApplicationSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .oauth2Login(AbstractHttpConfigurer::disable)
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/web/**", "/oauth2/**", "/login/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/web/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(withDefaults())
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()
            )
            .build();
    }
}
~~~

**This is a structural template** that must be adjusted to run with your OIDC provider's actual login/callback routes:

- Browser `oauth2Login()` needs an **OAuth2 client registration**, redirect URI/callback, and matching authorization-request repository.
- The default OAuth2 authorization-request endpoint is typically `/oauth2/authorization/{registrationId}`; the default OAuth2 login callback is typically `/login/oauth2/code/{registrationId}`. The browser chain's `securityMatcher` must cover the actual endpoints in use.
- A browser login may need a public GET `/login` or a custom login page; in the template above, those URLs are not yet configured as a full policy. Configure public entrypoints properly to avoid redirect loops.
- Do not disable CSRF on the browser chain just because the API chain disabled it. Browsers with cookies/sessions need proper CSRF policies.
- Saved requests in the browser chain can help return users to their starting page, though not every OIDC design requires them.
- These chains are an **alternative** to the global chain in section 5; do not copy all illustrative `SecurityFilterChain` beans into the same project.

### 7.3. Why not branch solely on `Accept`?

A machine caller can send:

~~~http
Accept: */*
~~~

Browser JavaScript can also send:

~~~http
Accept: application/json
~~~

And a browser tab can load a JSON API directly. The `Accept` header states the **desired representation**, not proof of whether the client is a browser, allowed to log in, or holds a session. Security policies should be classified by **endpoint/chain scope and client contract**, not merely user-agent or content negotiation.

### 7.4. Benefits of separating subdomains/ports

A system may separate:

~~~text
https://app.example.test         → OIDC browser client/session
https://api.example.test         → Bearer Resource Server
~~~

This clarifies trust boundaries and cookie scopes, yet does not by itself guarantee safety. DNS, TLS, CORS, cookie domain/path, gateway routing, and fallback chains must still be designed properly. If sharing one deployment, verify which path/host the security matcher actually sees behind the reverse proxy.

### 7.5. BFF and machine-called APIs are two different architectures

A browser-facing **Backend for Frontend (BFF)** can hold access tokens **server-side**, communicate with the browser over protected session cookies, and call backend Resource Servers with Bearer tokens. The BFF may need login redirects, request caches, cookies, CSRF, and logout.

The **backend Resource Server** behind the BFF only sees tokens from the BFF and usually needs no redirects/logins. Mixing BFF and backend API roles can cause a layer to accidentally keep sessions or return HTML against contract.

If one application acts as both BFF and API, clearly define **which requests carry browser-auto-sent cookies** and which are protected by Bearer headers, applying CSRF, sessions, and entry points strictly within scope.

## 8. Accurate HTTP responses for machine callers

An API client cares about more than whether a response contains JSON. It needs the **right HTTP status**, standard Bearer challenges, stable response bodies, and zero unexpected redirects.

### 8.1. Cases to distinguish

| Request | Authentication result | Authorization result | Typical response |
|---|---|---|---|
| Missing Bearer token, protected endpoint | Unauthenticated | No valid principal | 401 + `WWW-Authenticate: Bearer` |
| Bearer JWT invalid signature | Failed | Not treated as valid principal | 401, usually `invalid_token` |
| Expired Bearer JWT | Failed | Not treated as valid principal | 401, usually `invalid_token` |
| Opaque token introspection `active=false` | Failed | Not treated as valid principal | 401, usually `invalid_token` |
| Valid Bearer token lacking scope | Succeeded | Fails HTTP rule | 403, possibly `insufficient_scope` |
| Valid Bearer token with sufficient scope | Succeeded | Passes HTTP rule | Proceeds to controller/service |
| Valid Bearer token yet caller does not own record | Succeeded | HTTP rule passes, domain policy fails | 403 or 404 per contract |
| Public endpoint, no token sent | No auth required | `permitAll()` | Normal public response |
| Public endpoint, invalid token sent to Bearer chain | Bearer filter may reject invalid token | Never reaches `permitAll` | Possibly 401, 200 not guaranteed |
| Introspection endpoint timeout | No trustworthy verification result | No principal created | Auth/service error per policy; **never 302 login** |

**Rejecting a request** does not always mean 401: 401 typically relates to authentication requirements, while 403 relates to post-authentication access rights. `ExceptionTranslationFilter`, entry points, and access-denied handlers may pick different statuses depending on context.

### 8.2. `WWW-Authenticate` is part of the Bearer contract

Per RFC 6750, a Resource Server uses the HTTP `WWW-Authenticate` challenge to signal Bearer authentication requirements. Examples:

Missing credential:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Invalid credential:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Valid credential lacking scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Some responses may include `realm`, `error_description`, or `scope` when appropriate, though not every response must include all parameters. **Never put token values, raw JWT claims, secrets, or stack traces** into `error_description`.

### 8.3. Never turn authentication errors into HTTP 200

Another anti-pattern alongside redirects:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "success": false,
  "error": "NOT_AUTHENTICATED"
}
~~~

This is a **wrong-HTTP-layer** response for a standard API with status-code contracts. API gateways, monitors, and HTTP clients see 200 and may treat the request as successful. On authentication failure, keep 401; on insufficient post-auth permissions, keep 403.

### 8.4. Avoid leaking internal causes in error JSON

Never return:

~~~json
{
  "error": "JWT verification failed using https://internal-jwks...",
  "authorization": "Bearer <RAW_TOKEN>",
  "stackTrace": "...",
  "introspectionClientSecret": "..."
}
~~~

A safe error DTO:

~~~java
public record ApiError(
    String code,
    String message,
    String requestId
) {}
~~~

Example JSON when authentication fails:

~~~json
{
  "code": "UNAUTHENTICATED",
  "message": "An access token is required or invalid.",
  "requestId": "36d58f3e-d3b9-4c4c-9767-8b2c88f55375"
}
~~~

A system-generated request ID enables correlation without putting raw tokens into logs. When customizing JSON bodies, **preserve HTTP status codes and Bearer challenges**; avoid handlers that "return a JSON body while accidentally dropping `WWW-Authenticate`" or returning 200.

### 8.5. `Cache-Control` and personalized APIs

For responses carrying identity or private data, you may apply:

~~~http
Cache-Control: private, no-store
~~~

This is an **HTTP response cache** policy, not a request cache. It does not remove saved requests from a session. Conversely, `NullRequestCache` does not automatically emit `Cache-Control` headers for business responses.

Not every public response must be `no-store`; evaluate sensitivity, CDNs, proxies, ETags, and the API contract. However, error responses containing auth details or personal data must never be cached or exposed outside design bounds.

## 9. Customizing JSON errors without breaking the Bearer challenge

Many APIs require a consistent JSON body such as:

~~~json
{
  "code": "TOKEN_INVALID",
  "message": "Authentication failed."
}
~~~

That need is reasonable, yet merely replacing `AuthenticationEntryPoint` with a JSON-writing handler can drop protocol metadata. A safe design must:

1. Preserve **status 401** for authentication errors.
2. Preserve `WWW-Authenticate: Bearer` with framework-supplied parameters when appropriate.
3. Write only allowlisted body fields.
4. Never echo unchecked exception messages.
5. Never attempt to write a body if the response is already committed.
6. Handle **403 access denied** separately.

### 9.1. Using the built-in Bearer entry point is simplest

If the API does not require a custom JSON body, let Spring Security handle it:

~~~java
http.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(withDefaults())
);
~~~

When multiple authentication mechanisms/exception handlers exist, explicitly configure `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler` in `exceptionHandling` as shown in section 5.5.

### 9.2. Custom handlers must check whether the response is committed

One strategy is **delegating to the default Bearer handler to set status/challenge first**, then writing a short JSON body only if the response is not yet committed. Ensure the implementation aligns with the Servlet lifecycle and Spring Security exception handling.

Pseudo-code:

~~~text
on AuthenticationException:
  call BearerTokenAuthenticationEntryPoint
  if response is not committed:
      set Content-Type application/json
      write public ApiError with fixed code/message
  do not redirect
~~~

Never build headers by concatenating unescaped exception messages, tokens, or arbitrary `scope` values. Nor should you catch every runtime exception and return 401: a database outage or JSON serialization bug is a server error, not proof of an invalid token.

### 9.3. `@RestControllerAdvice` does not replace filter entry points

A `@RestControllerAdvice` handles exceptions from MVC controllers, yet authentication failures can occur **inside the Spring Security filter chain before reaching `DispatcherServlet`**. Thus:

~~~java
@RestControllerAdvice
class ApiExceptionAdvice {
    // ... handlers for business errors from controller
}
~~~

is not guaranteed to catch `AuthenticationException`/`AccessDeniedException` thrown by filters. Customize the proper security boundary via `AuthenticationEntryPoint` and `AccessDeniedHandler` when controlling Resource Server auth errors.

### 9.4. When upstream introspection errors occur

With opaque tokens, a timeout/503 from introspection means **unable to verify**. Never construct a "temporary" principal or redirect users to login. The system may apply a 503 service-error policy if designed with proper exception mapping; `active=false` results remain invalid tokens.

Key distinctions:

~~~text
Introspection result active=false → invalid token
Introspection unavailable          → unknown token status, fail closed
JWT signature invalid              → invalid token
Bearer valid but no authority      → authenticated, forbidden
~~~

A catch-all handler collapsing every case into a 302 login or 200 HTML destroys the distinction between authentication, authorization, and availability.

## 10. CSRF, CORS, and request cache do not replace each other

These three mechanisms have similar-sounding names in web config yet protect against different issues.

| Mechanism | Problem addressed | Involves redirect/login? |
|---|---|---|
| **RequestCache** | Retains saved request for browser login | Yes, tied to navigation/redirects |
| **CSRF protection** | Stops state-changing requests exploiting browser-auto-sent credentials | Tied to browser cookies/sessions |
| **CORS** | Defines which browser origins may read cross-origin responses and send certain requests | Tied to browser network policy, not token validation |
| **Bearer authentication** | Verifies caller's access token | Needs no interactive login redirect |
| **HTTP response cache** | Allows/prevents response caching in browsers/proxies/CDNs | Independent of saved requests |

### 10.1. CORS preflight does not carry Bearer tokens like actual requests

Browser JavaScript wanting to call:

~~~http
GET /api/orders/42 HTTP/1.1
Origin: https://app.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

may send a preflight first:

~~~http
OPTIONS /api/orders/42 HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflights normally **carry no Bearer token**, so they must be handled by the CORS processor before security authentication rejects them like an ordinary API request.

In Servlet:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

http.cors(withDefaults());
~~~

And a CORS source:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.test"));
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE", "OPTIONS")
    );
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type")
    );

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

This example is purely an illustrative policy; actual origins/methods/headers must follow the client contract. Never open `allowedOrigins("*")` with credential-bearing browser requests without evaluating browser CORS semantics and risks.

### 10.2. `OPTIONS /** → permitAll` is not enough to replace CORS

A rule:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

does not automatically generate the required `Access-Control-Allow-*` headers. It also permits non-preflight OPTIONS requests at the authorization layer. Prefer an **accurate CORS config** over opening all OPTIONS requests to fix browser errors.

### 10.3. `permitAll` does not mean skipping validation of invalid Bearer tokens

A permitted public endpoint:

~~~java
.requestMatchers("/api/public/**").permitAll()
~~~

does not guarantee a client sending `Authorization: Bearer invalid-token` to that endpoint will receive 200. If the Bearer authentication filter attempts to validate the header and finds an invalid token, it may reject the request before `permitAll` runs. To separate public endpoints from Bearer authentication, design chains/filters explicitly rather than changing authorization rules alone.

### 10.4. CSRF can cause 403 even with a valid token

If an application keeps CSRF protection enabled on POST, a request:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <VALID_TOKEN>
Content-Type: application/json

{"productId":"sku-123"}
~~~

can return `403 Forbidden` for missing a CSRF token, even when the JWT is valid and has `SCOPE_orders.create`. That **is not necessarily due to a missing scope**. If this is a pure header-based Bearer API, evaluate CSRF policy per threat model; if browser sessions/cookie auth are present, retain appropriate protection.

### 10.5. Security headers still matter

An API without session/redirect login still benefits from Spring Security-supported security headers, such as preventing caching of sensitive data, mitigating certain sniffing attacks, HSTS over HTTPS, and other product-specific headers.

Never use `web.ignoring()` on an entire API just to bypass request caching or form login: that can bypass other protective Spring Security filters. Instead, configure the security chain with Bearer authentication and `NullRequestCache`.

## 11. WebFlux: do not use web session request cache for pure Bearer APIs

In Spring WebFlux, components have different names than in Servlet:

| Responsibility | Servlet | WebFlux |
|---|---|---|
| HTTP security | `HttpSecurity` | `ServerHttpSecurity` |
| Chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Stateful saved request cache | `HttpSessionRequestCache` | `WebSessionServerRequestCache` |
| Non-saving request cache | `NullRequestCache` | `NoOpServerRequestCache` |
| Non-persisting security context | `NullSecurityContextRepository` / stateless policy | `NoOpServerSecurityContextRepository` |
| Resource Server JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque token introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Authorization | `authorizeHttpRequests` | `authorizeExchange` |
| Catch-all rule | `anyRequest()` | `anyExchange()` |

WebFlux uses reactive `WebSession` instead of Servlet `HttpSession`, yet can still produce cookies/sessions and redirects when browser login is enabled. Moving from Spring MVC to WebFlux **does not automatically make every app stateless**.

### 11.1. Reactive Resource Server without saved requests

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersApiSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .requestCache(cache -> cache
                .requestCache(NoOpServerRequestCache.getInstance()))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/public/status")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

This is the **WebFlux alternative** to Servlet, not a bean to mix casually into the same application stack. It demonstrates:

- `NoOpServerRequestCache` to avoid saving requests for login redirects.
- `NoOpServerSecurityContextRepository` to avoid persisting security context into a web session via this repository.
- Form login and HTTP Basic disabled on the API chain.
- JWT Resource Server validating Bearer tokens.
- CSRF disabled solely under the assumption of a pure header-based Bearer API with no cookie-based auth.

If using `oauth2Login()` on another reactive browser chain, apply appropriate session/CSRF/login policies; do not apply `NoOpServerRequestCache` blindly to every chain without considering login needs.

### 11.2. Reactive opaque tokens

If the API authenticates via introspection:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(withDefaults()))
~~~

The request cache and session repository settings can retain the same API policy. In WebFlux, introspection runs through `ReactiveOpaqueTokenIntrospector`. Do not treat Servlet `OpaqueTokenIntrospector` as proof a reactive app is configured properly; the two stacks use different interfaces.

### 11.3. Do not assume "non-blocking = no session"

Reactor does not automatically eliminate state such as:

- `WebSession` used for browser authentication.
- Cookies created by services/gateways.
- Request cache for interactive logins.
- OAuth2 Authorization Request/State repositories.
- Backend session stores for BFFs.

Define policies **by request path and client contract**. A reactive app can still be a purposefully stateful web application, while a machine-to-machine API must avoid sessions.

### 11.4. Reactive entry points and WebFlux security chains

Spring Security Reactive Resource Server provides handlers/entry points for Bearer authentication distinguishing 401/403 per Bearer semantics. When customizing `ServerAuthenticationEntryPoint` or `ServerAccessDeniedHandler` to return JSON bodies:

1. Never return 302 login for APIs.
2. Never omit the Bearer challenge when required.
3. Never write sensitive response bodies.
4. Never create an authenticated principal when a token is invalid/introspection unavailable.
5. Never use blocking operations while handling errors on the event loop.

Errors occurring inside a security `WebFilter` chain are likewise not handled automatically by controller-layer `@RestControllerAdvice`.

## 12. Real-world clients: cURL, backend services, mobile, and browsers

### 12.1. cURL calling a machine-to-machine API

With a mock token:

~~~bash
curl -i \
  -H 'Accept: application/json' \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' \
  https://orders-api.example.test/api/orders/42
~~~

What to observe:

- Valid token, sufficient scope → business response per contract.
- No token → 401 Bearer challenge.
- Invalid token → 401 `invalid_token`.
- Authenticated token lacking scope → 403.
- Never receives 302 login for any of these authentication failures.

In real shells, **never store production tokens in shell history, tickets, or logs**. Use proper credential-protection practices. Examples use placeholders, not directly runnable commands carrying real tokens.

### 12.2. Avoid auto-following redirects when diagnosing

To see the original 302 clearly:

~~~bash
curl -i https://orders-api.example.test/api/orders/42
~~~

Do not pass `-L` when checking whether the API returns a redirect, because `-L` makes cURL follow redirects and may show only the final response. With other HTTP clients, likewise distinguish the **initial response** from the **post-redirect-chain response**.

If a test merely asserts "eventually received HTTP 200" while the HTTP client silently followed a 302 to a login page, it is not properly testing the Resource Server contract.

### 12.3. Backend `RestClient` or `WebClient`

A backend calling the Orders API typically:

~~~text
1. Obtains an access token via valid OAuth 2.0 client credentials/token management.
2. Calls the API with Authorization: Bearer <token>.
3. 401 → handles invalid/expired token per policy; does not open browser login.
4. 403 → missing permission; does not self-grant additional scopes.
5. 503 → upstream auth/service failure if classified; bounded retries per contract.
~~~

For unexpected 302s, HTTP clients should enforce strict redirect policies: never forward Bearer credentials to origins outside the trust boundary, and never treat HTML login responses as successful JSON. Best of all is having the **Resource Server return proper 401/403 from the start**, rather than forcing every client to work around server bugs.

### 12.4. Mobile/desktop clients

A mobile app can use **system-browser OAuth 2.0 Authorization Code + PKCE** for users to log in and obtain tokens. Yet that is the **app's OAuth2 client** responsibility, not the Resource Server returning 302 to form login upon receiving an invalid Bearer token.

Mobile clients must distinguish:

~~~text
Login/token acquisition flow  ≠  protected resource request
~~~

A 401 from a protected resource can trigger client token management or prompt the user to re-authenticate **via the designed flow**, rather than blindly following arbitrary `Location` headers.

### 12.5. APIs called from browser JavaScript

A browser can be an API client, yet "called from a browser" does not turn an endpoint into a browser-login route. If JavaScript sends access tokens in `Authorization` headers per the chosen architecture, the API should still return Bearer 401/403 semantics. The frontend decides whether to navigate the user to login or display an error.

If using a BFF/session cookie instead of JavaScript holding tokens, use a different contract: browser ↔ BFF uses cookies/sessions and CSRF; BFF ↔ Resource Server uses Bearer tokens. Configuration cannot simply be duplicated across both hops.

### 12.6. Proxies/gateways mishandling 401/302

A gateway may have an **auth redirect plugin** configured or rewrite 401 errors into 302 redirects to an SSO portal. That suits web UIs yet breaks machine API clients. Even when Spring Security returns Bearer 401, clients may still receive 302 **because the gateway altered the response**.

Clarify:

- Which API routes must never use interactive SSO redirects.
- Whether the gateway preserves `WWW-Authenticate` and 401/403 statuses.
- Whether ingress rewrites `Location` or `Set-Cookie`.
- Whether API hosts/paths are clearly separated from web login hosts/paths.
- Whether upstream IdP auth errors are turned into an HTML "Service Unavailable" page with status 200.

Tests hitting localhost alone do not prove the production gateway returns the right responses. Test from a network vantage point matching real machine clients.

## 13. HTTP methods, saved requests, and write-replay hazards

A browser login workflow typically begins when a user visits a protected **GET** page; after logging in, the browser returns to load that page. APIs, however, may use:

~~~http
POST /api/payments/transfer
PUT /api/orders/42
DELETE /api/orders/42
~~~

Never treat saved request + 302 as a safe retry/replay mechanism for such operations.

### 13.1. No guarantee POST bodies are preserved

`HttpSessionRequestCache` saves request info to restore navigation and must not be viewed as a **transactional HTTP request queue**. When a client POSTs JSON, what can happen is:

~~~text
POST /api/orders    → redirect login
GET /login          → login
GET /api/orders     → lacks the original JSON POST body
~~~

Even when a redirect type or HTTP client preserves method/body, automatically replaying side effects can create duplicate transactions if the system lacks dedicated idempotency semantics.

### 13.2. Idempotency is an independent concern

For payment/ordering endpoints, if a client must retry an HTTP request after a timeout, the API can use an **idempotency key** or transaction-identity mechanism per contract. That is **unrelated** to saving requests for browser login.

Keep these separate:

~~~text
Bearer authentication:
  Is the token valid and authorized to call the API?

RequestCache:
  Which URL should the browser return to after interactive login?

Idempotency:
  If a mutating request is retried, does it create duplicate side effects?
~~~

Separating these three questions prevents "using login redirects to handle expired tokens on POST" and accidentally corrupting business operations.

### 13.3. Redirects with Bearer credentials can violate trust boundaries

If an HTTP client forwards the Bearer header to a cross-domain redirect target, credentials can leak. Never treat uncontrolled `Location` responses as places to send access tokens. Nor should an API server rely on clients retaining Bearer headers across redirects to continue authentication.

For machine clients, the cleanest pattern is an **explicit authentication response (401/403)** paired with client-side token acquisition/retry policies per contract.

## 14. Testing that the API returns no login redirects

An `authorizeHttpRequests` test checking only scopes is insufficient. You must prove **missing tokens, invalid tokens, or missing scopes never push the API into browser login**.

### 14.1. Adding Spring Security Test

~~~gradle
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Spring MVC example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiWithoutRedirectTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingBearerTokenReturns401WithoutLoginRedirect()
            throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", containsString("Bearer")))
            .andExpect(header().doesNotExist("Location"));
    }
}
~~~

This test assumes the application context loads a Bearer security chain for `/api/orders/**` with an appropriate decoder/introspector configuration to start up. **No controller needs to exist** for an unauthenticated request to be blocked by security filters; if the endpoint is `permitAll`, pick another protected endpoint for the test.

### 14.2. Testing a valid principal lacking scope

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

@Test
void missingScopeReturns403WithoutLoginRedirect() throws Exception {
    mvc.perform(
            get("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_profile")
                ))
        )
        .andExpect(status().isForbidden())
        .andExpect(header().doesNotExist("Location"));
}
~~~

This is an **illustrative test method**, placed in a class with `MockMvc mvc` and matching imports as in the previous example. Spring Security Test's `jwt()` builds a mock authentication and **skips real JWT cryptographic verification**. It helps test HTTP authorization, not whether the decoder verifies issuer/audience/signatures.

If the API's `SecurityFilterChain` uses opaque tokens, use the corresponding `opaqueToken()` test helper to simulate principal/authorities, while testing real introspection separately.

### 14.3. Testing that no session is saved in a pure API

An additional test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void missingBearerDoesNotCreateHttpSession() throws Exception {
    var result = mvc.perform(get("/api/orders/42"))
        .andExpect(status().isUnauthorized())
        .andReturn();

    assertThat(result.getRequest().getSession(false)).isNull();
}
~~~

This check suits a **pure stateless API goal**. It can fail if another filter/controller/library intentionally creates an HTTP session; in that case, locate the session-creating component rather than simply claiming Spring Security's `STATELESS` "doesn't work."

Do not evaluate a browser chain with a "session must be null" test; browser login may legitimately need sessions to manage login/authorization requests by design.

### 14.4. Testing that no unexpected `Set-Cookie` is emitted

~~~java
@Test
void missingBearerDoesNotIssueSessionCookie() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().doesNotExist("Set-Cookie"));
}
~~~

The goal is catching an API defined as **cookie/session-free** unexpectedly issuing cookies. If the product intentionally emits an unrelated non-auth cookie, assert specifically on `JSESSIONID` or session cookie policies instead of forbidding all cookies unconditionally.

### 14.5. Checking 302 alone is not enough

A useful check verifies:

~~~text
Request:
  GET /api/orders/42
  Accept: application/json
  Authorization: missing

Expected:
  status = 401
  WWW-Authenticate begins with Bearer
  no Location: /login
  no HTML login body
  no saved request in HttpSession
~~~

If your HTTP client follows redirects automatically, configure **no redirect following** when asserting the original response. For production behind gateways/ingress, test through the gateway as well since gateways can rewrite 401 into 302.

### 14.6. Testing WebFlux with `WebTestClient`

For Spring WebFlux, an example test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveApiWithoutRedirectTest {

    @Autowired
    WebTestClient client;

    @Test
    void missingBearerReturns401Not302() {
        client.get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                "WWW-Authenticate", "^Bearer.*")
            .expectHeader().doesNotExist("Location");
    }
}
~~~

This test template assumes a WebFlux application context with matching Resource Server config/decoder. When running `WebTestClient` against a live server, ensure the client does not auto-follow redirects when testing for unwanted 302s.

### 14.7. For invalid tokens, test the real decoder

Mock `jwt()` tests HTTP scope policies, yet to prove the Bearer filter returns 401 for invalid tokens:

1. Use test-only JWTs signed with a real test private key, configuring the decoder to trust the matching test public key.
2. Send tokens in the `Authorization: Bearer ...` header rather than via mock post-processors.
3. Test invalid signatures, expired tokens, and wrong issuer/audience.
4. Assert 401 + proper challenge; no redirect.
5. Never use production signing keys or real access tokens in test fixtures/CI.

With opaque tokens, use an introspection stub/test Authorization Server environment for `active=true/false` and connection errors, confirming zero redirects.

## 15. Comprehensive test matrix for machine-called APIs

| Context | Request | Expectation per API contract |
|---|---|---|
| No token sent | GET protected URL | 401 Bearer, no 302 |
| Empty/malformed Bearer header | GET protected URL | Authentication rejected, no HTML login |
| JWT invalid signature | GET protected URL | 401 `invalid_token`, no 302 |
| Expired JWT | GET protected URL | 401, no saved request |
| Valid JWT missing scope | GET protected URL | 403, no redirect |
| Valid JWT with sufficient scope | GET protected URL | Controller/service runs, no session needed |
| Opaque token `active=false` | GET protected URL | 401, no redirect |
| Introspection timeout | GET protected URL | Unauthenticated; error per policy, no 302 |
| Public URL without token | GET `/api/public/status` | 200 if endpoint exists, no login required |
| Public URL with invalid token | GET `/api/public/status` | Bearer filter may return 401; test per exact chain |
| Valid CORS preflight | Cross-origin API OPTIONS | Proper CORS headers, no login redirect |
| Protected POST missing token | API POST | 401 under appropriate CSRF policy, no post-login replay |
| Valid-token POST missing scope | API POST | 403, no auto-login |
| URL outside API chain | GET `/internal/secret` | Protected by fallback chain, not left unprotected |
| Unauthenticated browser web URL | GET `/web/dashboard` | May 302 login per browser contract |
| Browser OAuth2 login callback | GET `/login/oauth2/code/...` | Handled by browser chain, not blocked by Bearer API chain |
| API via gateway | GET protected URL | Preserves 401/403, not rewritten to SSO redirect |
| API expecting JSON response | GET protected URL with invalid token | Never returns HTML `/login` with status 200 |
| End of unauthenticated request | GET protected URL | Creates no HTTP session if pure stateless required |

You cannot infer all these expectations from a single `sessionCreationPolicy(STATELESS)` line. Check **endpoint matchers, filter chains, entry points, request caches, gateway behavior, and HTTP clients**.

## 16. Common configuration mistakes and diagnostics

### 16.1. Receiving 302 to `/login` instead of 401

Possible causes:

- `formLogin()` is enabled on the security chain handling API URLs.
- `LoginUrlAuthenticationEntryPoint` is registered with too broad a matcher.
- A form-login chain without `securityMatcher` precedes the Resource Server chain.
- Gateway/SSO middleware rewrites 401 into 302.
- A custom entry point explicitly calls `sendRedirect(...)`.

Remediation steps:

1. Identify **which chain was selected for the API request**.
2. Inspect form/OAuth2 login and exception handling on that chain.
3. Place the specific Bearer API chain ahead of browser chains via `@Order` when using multiple chains.
4. Set `NullRequestCache` and a Bearer entry point on the API chain.
5. Inspect responses before and after the gateway to pinpoint where 302 originates.

**Do not** fix this by turning every URL into `permitAll()`, as that removes authorization rather than fixing the entry point.

### 16.2. Receiving HTTP 200 with an HTML login body

Usually the HTTP client **followed a 302** and the login page's final response was 200. Do not debug only the API controller; inspect the redirect chain:

~~~text
API request → 302 /login
GET /login → 200 text/html
~~~

Disable auto-follow redirects in your test tool or inspect full response history, then fix the server/gateway so the API returns Bearer 401/403.

### 16.3. `JSESSIONID` still appears despite `STATELESS`

Check:

- Is any browser login/CSRF filter in that chain?
- Does `RequestCache` still use an HTTP session on any chain?
- Does a controller/view engine/service create a session?
- Does Spring Session or middleware emit cookies?
- Does a reverse proxy add its own session/cookie?

`STATELESS` is Spring Security's persistence policy, **not a JVM-wide ban on Servlet sessions**. If a pure API must create zero sessions, locate the component creating it.

### 16.4. Replaced `NullRequestCache` yet API still redirects

`NullRequestCache` only prevents saving requests. If `formLogin()` or `oauth2Login()` still triggers for the API, the authentication entry point can still return **302 to login**. You need both the **right entry point/login mechanism** and the request cache policy.

~~~text
NullRequestCache:
    Does not save requests

BearerTokenAuthenticationEntryPoint:
    Uses 401 Bearer challenge

The first cannot substitute for the second.
~~~

### 16.5. Disabled `formLogin` yet API returns `WWW-Authenticate: Basic`

`httpBasic()` may still be enabled or another security chain was selected. Check Basic mechanisms and chain scopes. For a Bearer API, return a proper Bearer challenge rather than triggering unwanted browser Basic credential prompts.

### 16.6. 403 on POST even though Bearer token has scope

Possible causes:

- CSRF protection is requiring a CSRF token.
- Token authenticated yet lacks the authority for that specific method.
- HTTP matcher missed the path/method due to rule order.
- Business authorization denied owner/tenant access.

Do not treat every 403 as a CSRF error and disable CSRF globally. Identify **which layer rejected the request**. If the app also uses cookie/session auth, disabling CSRF opens severe vulnerabilities.

### 16.7. Unauthenticated request on public URL still returns 401

Check whether `permitAll()` matches the exact path/method, whether the security matcher fits, whether another chain takes precedence, or whether a gateway enforces auth separately. If a public request **carries an invalid token**, the Bearer filter may still return 401; that differs from a credential-less request.

### 16.8. `anyRequest().denyAll()` is set, yet one URL stays unprotected

If a URL matches **no `SecurityFilterChain` at all**, the API chain's catch-all does not apply. Provide a fallback chain or designed protection. Distinguish clearly:

~~~text
securityMatcher("/api/**")   → selects chain for /api/**
anyRequest().denyAll()       → catch-all within the selected chain
~~~

`anyRequest()` does not mean "the entire network/application" when a single chain has a scoped matcher.

### 16.9. OAuth2 Login callback blocked by the Bearer chain

If an API chain uses an overly broad matcher like `/**` ahead of the browser chain, it can intercept `/oauth2/authorization/**` or `/login/oauth2/code/**` and return 401 instead of processing OIDC callbacks. Set `securityMatcher` and `@Order` accurately to separate interactive login flows.

### 16.10. One API accepting both cookies and Bearer headers

If an endpoint accepts both session cookies and Bearer tokens, **which authentication mechanism takes precedence** and **which CSRF policy applies** become critical. Never just add `STATELESS` and assume cookies stopped taking effect. Often it is cleaner to separate endpoints/hosts/chains or accept a single authentication mechanism at the API boundary.

### 16.11. Cross-origin redirects and Authorization headers

Do not rely on default HTTP client behavior to protect credentials when a server returns cross-origin redirects. Some clients strip `Authorization`, while others vary by library/version/config. The right design is for APIs **never to redirect to login** and for clients never to forward tokens to origins outside an allowlist.

### 16.12. Post-authentication 404/405 mistaken for a Bearer error

If the token authenticated properly and Spring MVC/WebFlux cannot find the route/method, the app returns 404 or 405. Never "fix" this by enabling form login or changing request cache; first verify whether authentication/authorization succeeded, then inspect controller mappings. Under `anyRequest().denyAll()`, unclassified URLs may also receive 403 before reaching controllers.

### 16.13. `Accept: text/html` causes API to redirect when token is missing

If an app uses multiple entry points driven by content negotiation, the `Accept` header can influence selection. Yet machine APIs still need a **Bearer contract scoped by endpoint**, never switching to browser login policy just because a client sent an unusual `Accept` header. Configure dedicated chains or matchers for APIs instead of relying solely on `Accept`.

### 16.14. Request cache disabled while `SavedRequestAwareAuthenticationSuccessHandler` remains

A browser-login handler might remain wired in the chain; when request cache saves nothing, it may use a default target URL or another fallback. If the API has no interactive login, **no browser success handler is needed**. Keep saved requests/success handlers in the browser chain rather than bringing them into the Resource Server.

### 16.15. Disabling `RequestCacheAwareFilter` by bypassing all of Spring Security

Never use `web.ignoring("/api/**")` or strip the security filter chain just to avoid saving requests. Doing so can disable token authentication, authorization, security headers, and other defenses. `NullRequestCache` is the **targeted** solution.

## 17. Workflow for diagnosing 302s from an API

When a machine caller reports "the API returned a login page," follow this decision flow:

~~~mermaid
flowchart TD
    A["Machine client receives HTML/302"] --> B{"Did initial response return 302?"}
    B -->|No| C["Check gateway rewrite, content type, custom error handler"]
    B -->|Yes| D{"Where does Location point?"}
    D -->|"/login"| E["Form login / LoginUrlAuthenticationEntryPoint / gateway"]
    D -->|"IdP authorization endpoint"| F["OAuth2 Login / SSO middleware"]
    D -->|"Other host"| G["Custom redirect / gateway / proxy"]
    E --> H["Identify selected SecurityFilterChain"]
    F --> H
    G --> H
    H --> I{"Does API chain have Bearer entry point and NullRequestCache?"}
    I -->|No| J["Configure dedicated API chain without interactive login"]
    I -->|Yes| K["Check custom filters/exception handling and upstream"]
    J --> L["Verify 401/403 with no Location, no session"]
    K --> L
~~~

### 17.1. Step 1: observe the raw response

Send the protected request **without a Bearer token** and **without following redirects**, and record:

~~~text
HTTP status
WWW-Authenticate
Location
Content-Type
Set-Cookie
Cache-Control
~~~

Never put raw tokens into tickets/logs. If testing with invalid credentials, use a synthetic token from a test issuer or a non-usable invalid string.

### 17.2. Step 2: locate where the redirect originates

If calling the application directly returns 401 yet calling through the gateway returns 302, the fault is in the gateway/SSO middleware. If the app itself returns 302 before the gateway, inspect Spring Security chains, entry points, and login mechanisms.

### 17.3. Step 3: identify the selected chain

With multiple chains:

~~~text
@Order(1) /api/**  → Bearer API
@Order(2) /web/**  → Browser login
@Order(3) fallback
~~~

Inspect the actual request path reaching the servlet after reverse proxies, context paths, and servlet paths—not just the public gateway URL. A mismatched API matcher can send requests into the browser fallback.

### 17.4. Step 4: inspect RequestCache and sessions

The API chain needs `NullRequestCache` if it has no saved-request workflow. `STATELESS` expresses the intent not to persist security context via HTTP sessions. If a session still appears, locate the filter/library creating it rather than guessing solely from a 302 status.

### 17.5. Step 5: re-verify 401/403 and POST cases

After updating configuration:

- Protected GET without token → 401 Bearer.
- Protected GET with invalid token → 401, no redirect.
- Protected GET missing scope → 403.
- Protected POST without token → proper auth error, no login/replay.
- Unauthenticated browser web route → still redirects per browser contract.
- Gateway preserves API status/headers.

Never declare success just because a valid-token request returns HTTP 200; request-cache/redirect bugs usually surface only on **failure paths**.

## 18. Design options when API and web cannot be separated by path

Some legacy systems share URLs between browser sessions and machine clients:

~~~text
GET /orders/{id}

Browser:
  cookie session → HTML page

Machine:
  Authorization Bearer → JSON representation
~~~

This architecture can work, yet requires **deliberate separation of security mechanisms**, rather than relying solely on `Accept: application/json`.

### 18.1. Multiple `AuthenticationEntryPoint`s by matcher

Spring Security supports exception handling that selects an authentication entry point by `RequestMatcher`. However, when APIs and browsers share paths, entry-point selection criteria must be explicitly defined:

- Host/subdomain or port.
- An application-controlled URL prefix.
- Endpoint contract explicitly marking whether the response is API or web page.
- Allowed security chain type and authentication mechanisms.

**Never treat User-Agent, `Accept` headers, or "no cookie" as security proof.** Those values are caller-controlled or unstable.

### 18.2. Prefer splitting API boundaries when possible

A refactoring path:

~~~text
Before:
  /orders/{id} + session/form login or bearer

After:
  /web/orders/{id} → browser login/session
  /api/orders/{id} → Bearer API/stateless
~~~

This requires updating routing, session cookie scope, CORS, CSRF, reverse proxies, and clients, yet yields an easier-to-audit security policy with far fewer accidental redirects.

### 18.3. If both credential types must be supported

Write a contract answering these questions:

1. If a request carries both a session cookie and a Bearer header, **which credential takes precedence**?
2. If the Bearer token is invalid yet the cookie is valid, may the API fall back to the cookie?
3. If session login succeeded yet Bearer authority is missing, should the request be allowed?
4. Which HTTP methods does the CSRF filter apply to?
5. Is `WWW-Authenticate` preserved for machine callers?
6. Can a Bearer request emit a session cookie?
7. Can a Bearer request create a saved request?
8. Does domain authorization read the principal from the right source?

A policy lacking clear answers risks **credential confusion**: the API trusts a principal from a different mechanism than the one the client believed it was using. Separating security chains or API surfaces usually prevents this class of bug.

### 18.4. Do not route all errors to a unified login page

A system with a shared SSO error page might try redirecting all 401/403 errors. For machine API clients, that breaks the HTTP contract and can amplify IdP load when clients auto-follow/retry.

Distinguish clearly:

~~~text
Browser web:
  unauthenticated → approved interactive login redirect

Bearer API:
  unauthenticated → 401 Bearer challenge
  authenticated but unauthorized → 403
  upstream auth unavailable → fail closed, service error per policy
~~~

## 19. Self-check questions

**Q1.** What problem is `HttpSessionRequestCache` designed to solve?

It retains a saved request so the browser can return after interactive login. It is **not** a token cache, API retry queue, or HTTP response cache.

**Q2.** Why is `NullRequestCache` suited for pure Bearer APIs?

Because machine clients do not need URLs saved while awaiting browser login and redirection. With `NullRequestCache`, Spring Security does not save/restore saved requests via that component.

**Q3.** Does setting `NullRequestCache` alone guarantee an API returns 401 instead of 302?

**No.** If form login/OAuth2 Login entry points still apply to the API, the server can still redirect even without saving requests. You need both a Bearer entry point and the right chain policy.

**Q4.** Does setting `SessionCreationPolicy.STATELESS` alone stop every component from creating a session?

**No.** It governs how Spring Security uses sessions for security context; it does not forbid application code, controllers, view engines, or libraries from creating Servlet sessions.

**Q5.** When an API is missing a Bearer token, what status code is typically expected?

**401 Unauthorized** with `WWW-Authenticate: Bearer`. Never redirect to a browser login page merely because the API request is unauthenticated.

**Q6.** How should a valid JWT missing `SCOPE_orders.read` be handled?

Typically **403 Forbidden**, without forcing the user to log in again to swap authorities. The client must request/manage permissions through proper OAuth/app flows.

**Q7.** Is OIDC browser Authorization Code using redirects wrong?

No. Redirects are an intentional part of interactive login flows. The mistake is applying that flow to protected Resource Server APIs called by machines with Bearer tokens.

**Q8.** Why might a client report HTTP 200 while its JSON parser fails on character `<`?

The client likely followed a 302 to a login page and received 200 HTML. Inspect the initial response, `Location`, and `Content-Type` rather than only the final status.

**Q9.** When an API uses CORS, must you open all OPTIONS requests with `permitAll`?

No. Configure the CORS processor and appropriate origin/method/header sources; broad OPTIONS rules neither emit CORS headers nor avoid over-exposing requests.

**Q10.** Why shouldn't CSRF be disabled on every chain in a hybrid application?

Browser session/cookie authentication is exposed to CSRF because browsers auto-send credentials. Disabling CSRF may fit pure header-based Bearer APIs, yet is unsafe by default for web login/BFFs.

**Q11.** When should multiple `SecurityFilterChain`s be used?

When an application has URL areas needing different authentication mechanisms, entry points, or session policies—such as `/api/**` with Bearer and `/web/**` with OIDC browser login. Control `@Order` and `securityMatcher` carefully.

**Q12.** Does one `anyRequest().denyAll()` in the API chain protect all URLs in the application?

No. It applies only to requests that selected that chain. With multiple chains, include an appropriate fallback so no route falls outside protection.

**Q13.** Should a tokenless POST be saved and automatically replayed after login?

Not for machine API clients. Request cache is not a transactional queue; replaying writes can corrupt methods/bodies or create duplicate side effects. The API should return an auth error, while retries/idempotency belong to client and business contracts.

**Q14.** If the Resource Server returns 401 yet the gateway returns 302, where is the fix?

Fix the gateway/SSO rewrite policy for APIs while verifying upstream Spring Security returns the right Bearer challenge. Test through the real gateway.

**Q15.** When introspection times out, does a login redirect help the Resource Server verify the token?

No. An introspection infrastructure failure means no proof of a valid token exists, so no principal may be created. Redirecting to login does not replace token verification and only breaks machine error handling.

## 20. Machine-called API configuration checklist

### 20.1. Scope and authentication

- [ ] Identified which endpoints are **Bearer Resource Server APIs** and which serve browser login.
- [ ] API chain has an appropriate `securityMatcher` when multiple chains exist.
- [ ] `@Order` ensures browser login chains do not intercept APIs first.
- [ ] A fallback chain exists for URLs outside categorized areas.
- [ ] JWT decoder/introspection source configured with trusted issuer, audience, and token profile.
- [ ] HTTP authorization enforced by method/scope, not merely `anyRequest().authenticated()` everywhere.
- [ ] Resource ownership/tenant rights additionally enforced in services where needed.

### 20.2. State, saved requests, and login

- [ ] API chain disables form login/OAuth2 interactive login if serving only machine callers.
- [ ] API chain uses `NullRequestCache` or `NoOpServerRequestCache` per stack.
- [ ] Decided session/context persistence policy: `STATELESS` or reactive no-op repository per architecture.
- [ ] No unintended filter/controller creates `JSESSIONID`/web sessions for pure APIs.
- [ ] Raw Bearer tokens, Authorization headers, or JSON POST bodies are never stored in saved requests/sessions.
- [ ] Browser chain retains login redirects/CSRF/sessions properly without being broken by API policies.
- [ ] OAuth2 authorization endpoint and login callbacks sit inside the proper browser chain.

### 20.3. HTTP behavior and web security

- [ ] Missing Bearer → 401, never 302.
- [ ] Invalid token → 401 `invalid_token` (when applicable), never 302 or 200 HTML.
- [ ] Valid token lacking authority → 403, no redirect.
- [ ] `WWW-Authenticate: Bearer` is preserved by custom handlers and gateways.
- [ ] Raw tokens/claims/exception stack traces are never returned in error bodies.
- [ ] CORS preflight handled per origin/method/header policy.
- [ ] CSRF protected on browser/cookie flows; disabled only where the API threat model permits.
- [ ] Response cache and sensitive data headers configured separately.
- [ ] No open redirects or cross-origin redirects carrying Bearer tokens.
- [ ] Gateway does not rewrite API 401s into SSO login redirects.

### 20.4. Testing and observability

- [ ] Tests cover missing token, invalid token, missing scope, and valid token.
- [ ] Tests verify no `Location: /login` and no HTML login after authentication errors.
- [ ] Tests verify no session cookie/saved request emitted on stateless API paths.
- [ ] Tests verify browser routes still log in/callback per contract.
- [ ] Tests cover CORS preflights and POSTs under actual CSRF policies.
- [ ] Tests verify URLs outside the API chain hit the fallback policy.
- [ ] Tests run through the gateway with auto-follow redirects disabled.
- [ ] Separate tests verify **real** JWT signatures/introspection, not just `jwt()`/`opaqueToken()` post-processors.
- [ ] Logging/tracing never records raw access tokens, session IDs, or secrets.
- [ ] Error/redirect metrics distinguish 401/403/302 by route/chain to catch regressions.

A public endpoint with `permitAll` does not mean requests skip all filters. A stateless API does not mean the entire application creates no sessions. And an API using OAuth 2.0 does not mean it must itself perform **OAuth2 Login redirects**: preserve its proper **Resource Server** role.

## 21. Summary

Decision diagram for machine-to-machine APIs:

~~~text
                 Machine client calls protected API
                                |
                                v
                   API-dedicated SecurityFilterChain
                                |
          +---------------------+---------------------+
          |                     |                     |
      No Bearer          Bearer invalid          Bearer valid
          |                     |                     |
          v                     v                     v
     401 + Bearer        401 invalid_token     HTTP authorization
      challenge         (no login redirect)          |
          |                     |              +-----+------+
          |                     |              |            |
          |                     |         Missing scope  Scope OK
          |                     |              |            |
          v                     v              v            v
    No saved request     No saved request     403       Controller
    No login redirect    No login redirect  forbidden   + domain auth

    Session policy:    stateless Bearer handling
    Request cache:     NullRequestCache / NoOpServerRequestCache
    Browser login:     a separate chain, only if the product needs it
~~~

**Key points to remember:**

1. **Request cache serves browser navigation**, not API Bearer token verification, retries, or storage. For pure machine-called APIs, choose `NullRequestCache` or `NoOpServerRequestCache`.
2. **Login redirects belong to interactive clients.** Resource Server APIs must preserve Bearer challenges and clear HTTP errors; never turn 401/403 into 302 or 200 HTML.
3. **Stateless does not mean the server can never create sessions.** `SessionCreationPolicy.STATELESS` governs Spring Security's session usage, while request caches and other application components need separate configuration.
4. **Separate security policies by scope** when an application serves both browser OIDC login and Bearer token APIs. Each `SecurityFilterChain` gets its own entry point and CSRF/CORS/session/request-cache policy per contract.
5. **Web security is more than request caching.** CSRF for cookie-based browser flows, CORS for cross-origin browsers, HTTP security headers, token validation, and domain authorization remain distinct responsibilities.
6. **Testing failure paths matters just as much as happy paths:** missing tokens, invalid tokens, missing scopes, introspection outages, gateway redirects, session cookies, and preflights all require clear expectations.

The ultimate goal is not "turning off every Spring Security component," but applying **the right mechanism to each client type**: browsers may need login redirects and saved requests; Resource Servers serving machine callers need **Bearer authentication, appropriate state, and predictable HTTP responses**, never turning token errors into a detour through a login page.

## References

- [Spring Security — RequestCache](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Servlet Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Servlet OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — Servlet Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Security — Reactive Session Management](https://docs.spring.io/spring-security/reference/reactive/authentication/session-management.html)
- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9110 — HTTP Semantics (Status Codes and Redirection)](https://www.rfc-editor.org/rfc/rfc9110)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
