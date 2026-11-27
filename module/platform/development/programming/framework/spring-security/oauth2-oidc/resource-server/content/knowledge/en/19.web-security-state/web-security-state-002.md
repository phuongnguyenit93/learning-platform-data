# SessionCreationPolicy.STATELESS and Components That Can Create State

In **Spring Security OAuth 2.0/OIDC Resource Server**, a common configuration is:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

Many people interpret this line as: "The application never has an `HttpSession`, never creates cookies, holds no state whatsoever, and every request is completely independent." **That conclusion is overly broad.**

The core meaning of `SessionCreationPolicy.STATELESS` is that **Spring Security does not create an `HttpSession` to maintain authentication and does not use an `HttpSession` to obtain the `SecurityContext`**. It does not forbid controllers, other servlet filters, Spring MVC, CSRF repositories, OAuth2 Login, third-party libraries, or external infrastructure from creating/storing state through their own mechanisms.

A REST API that only uses bearer access tokens in the `Authorization` header typically **does not need to save authentication in an HTTP session**: each request provides a token and is verified anew. However, other kinds of state can still exist, such as JWKS caches, introspection caches, databases, rate limiting, CSRF tokens, login state, cookies, or an HTTP session created by another component.

> **Key message:** `STATELESS` is a **Spring Security session management policy**, not a guarantee that "the entire application has no state." To ensure an endpoint truly creates no `HttpSession`, you must inspect the filter chain, other Spring Security components, and the entire Servlet/Spring MVC processing flow.

This lesson distinguishes the four session creation policies, the roles of `SecurityContextRepository` and `RequestCache`, hidden sources of state creation, how to structure a REST Resource Server alongside OIDC Login, and methods for testing/diagnosing `JSESSIONID`.

## 1. Starting from the requirements of an OAuth 2.0 Resource Server

With a JWT bearer token, a client typically calls the API:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

The Resource Server verifies the signature, issuer, audience, expiration, scopes, and other contract conditions. If the token is valid, Spring Security creates an `Authentication` in `SecurityContext` for components of the **current request** to use.

~~~text
Request A: Authorization: Bearer token-123
   |
   v
BearerTokenAuthenticationFilter
   |
   v
JwtDecoder + claim validators
   |
   v
SecurityContext(Authentication for A)
   |
   v
AuthorizationFilter -> Controller -> Response
   |
   v
End of request: Authentication is not saved into HttpSession

Request B: Authorization: Bearer token-123
   |
   v
Verify token per policy for request B
   |
   v
SecurityContext(Authentication for B)
   |
   v
Authorization -> Response
~~~

In this model, the Resource Server **does not need to write `Authentication` into a session** to recognize the same client on the next request. The credential is the bearer token sent again.

The same can apply to opaque tokens:

~~~text
Bearer opaque token -> OpaqueTokenIntrospector -> Authentication
```

The main difference is how the token is verified: JWTs are typically checked locally by signature/JWKS, whereas opaque tokens typically call an introspection endpoint. **Both can use `SessionCreationPolicy.STATELESS`**, though introspection involves network calls and possibly caching.

### 1.1. Stateless authentication does not mean tokens are "stateless" everywhere

An Authorization Server can manage:

- Client registration, consent, and user permissions.
- Refresh tokens or AS-side login sessions.
- Token revocation or token-introspection state.
- Key rotation, JWKS, and metadata.
- Role/permission data and policies.
- Audit events or rate limits.

A Resource Server can also use public key caches, introspection results, memberships, denylists, rate limiters, or databases for authorization. **These data are not necessarily HTTP sessions.**

An API can be stateless at the **`SecurityContext` storage layer** while still using business and infrastructure state.

## 2. Four SessionCreationPolicy values

Spring Security has the enum `org.springframework.security.config.http.SessionCreationPolicy`.

| Policy | Expected Spring Security behavior | Key distinction |
|---|---|---|
| `ALWAYS` | Always creates an `HttpSession` | Suitable for certain session-oriented flows |
| `IF_REQUIRED` | Creates a session only when Spring Security needs one | A login/request cache flow can cause a session to appear |
| `NEVER` | Spring Security does not create a session itself, **but may use an existing session** | Not equivalent to `STATELESS` |
| `STATELESS` | Spring Security does not create an `HttpSession` and **does not use a session to obtain `SecurityContext`** | Does not prohibit code outside this scope from creating a session |

Their semantics are described in the `SessionCreationPolicy` Javadoc and Spring Security's session management documentation.

### 2.1. Distinguishing `NEVER` and `STATELESS`

This is a particularly important difference.

With `NEVER`:

~~~text
Request arrives at API
    |
    +-- Does an HttpSession already exist from another component?
             |
             +-- Yes -> Spring Security may use that session
             |
             +-- No -> Spring Security does not proactively create one
~~~

With `STATELESS`:

~~~text
Request arrives at API
    |
    +-- Does an HttpSession exist or not?
             |
             +-- Spring Security does not retrieve SecurityContext from it
             |
             +-- Bearer token authentication is verified per request
```

If the goal is **not relying on a session to authenticate the API**, `STATELESS` expresses that intent more clearly than `NEVER`.

However, if a controller still calls `request.getSession()`, the Servlet container **can create a session** even when the Security chain is configured with `STATELESS`.

### 2.2. `IF_REQUIRED` does not always create a session

If a request does not trigger a feature requiring a session, `JSESSIONID` might not appear even with `IF_REQUIRED`. Conversely, request cache, login, or CSRF can cause a session to appear when appropriate for the flow.

You cannot conclude whether a chain is stateful or stateless just by seeing a single response without cookies. You must inspect the configuration and actual processing paths.

## 3. `SecurityContextHolder` holds "state" but does not mean an HTTP session

Spring Security allows retrieving authentication:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

`SecurityContextHolder` typically uses a strategy storing the context bound to the thread currently executing the request (e.g., `ThreadLocal`). While the request runs, filters/controllers/services can read the same authentication for authorization.

This is **in-memory request-processing state**, not proof that an `HttpSession` or cookie was created.

### 3.1. Two different kinds of state

| Concept | Lifecycle | Purpose |
|---|---|---|
| `SecurityContext` in current request | Tied to request processing and security context lifecycle | Exposes principal and authorities to controllers/services |
| `HttpSession` | Typically persists across multiple requests, identified by session ID | Stores session data; can hold security context if config allows |
| Client-side JWT bearer token | Lives until expiry/revocation per policy | Credential sent by client on each request |
| JWKS cache | Retains keys for a period | Improves signature verification performance |
| Introspection cache | Retains token check results if configured | Reduces network calls but carries staleness risk |
| Redis/DB business state | Depends on business domain | Orders, tenants, permissions, rate limits |

Under `STATELESS`, having an `Authentication` in `SecurityContextHolder.getContext()` **is normal**. It does not mean `SecurityContext` was saved in an `HttpSession`.

### 3.2. Do not ignore lifecycle when writing custom filters

A custom filter must not put `Authentication` into a static variable or its own `ThreadLocal` and leave it there after the request. Spring Security provides mechanisms to manage and clear `SecurityContext` along the filter chain.

If creating authentication manually or handling async threads, use appropriate propagation/lifecycle mechanisms. Passing `SecurityContext` across `@Async`, executors, or reactive boundaries is a separate concern, **not a reason to turn on HTTP sessions**.

## 4. `SecurityContextRepository` decides where the security context is stored

Spring Security provides the `SecurityContextRepository` interface. Common implementations:

| Repository | Purpose |
|---|---|
| `HttpSessionSecurityContextRepository` | Loads/saves `SecurityContext` in `HttpSession` |
| `RequestAttributeSecurityContextRepository` | Uses request attributes, useful with other dispatchers within the same request |
| `DelegatingSecurityContextRepository` | Combines multiple repositories |
| `NullSecurityContextRepository` | Does not load/save `SecurityContext` via repository |

When `SessionCreationPolicy.STATELESS` is configured in the standard supported flow, Spring Security uses **`NullSecurityContextRepository`** so authentication is not persisted across HTTP sessions.

~~~text
JWT bearer request
   |
   v
Authenticated SecurityContext
   |
   +-- Controller uses it within the current request
   |
   +-- NullSecurityContextRepository:
       does not save context to restore on subsequent requests
```

### 4.1. What does `NullSecurityContextRepository` do?

It **does not save authentication** across requests. On subsequent requests, the Resource Server needs to verify the token sent again.

Absence of a session does not mean the API must reject the second request. If the client still sends a valid token on the second request, it can be authenticated normally.

### 4.2. Distinguishing `SecurityContextHolderFilter` and `SecurityContextPersistenceFilter`

In modern Spring Security architecture:

- `SecurityContextHolderFilter` reads the security context from the repository and makes it available to the request; **it does not automatically save it back**.
- `SecurityContextPersistenceFilter` from older flows/versions had a mechanism to save the context when needed after the request.
- If custom code wants to save authentication across requests, it must use `SecurityContextRepository.saveContext(...)` according to the corresponding configuration.

Spring Security 6 documentation explains that `SecurityContextHolderFilter` is the new default choice in many flows; **you should not configure both persistence and holder filters side by side**.

For a stateless REST bearer API, we **do not want** to save the context into `HttpSession` merely because authentication succeeded. If someone overrides the repository to `HttpSessionSecurityContextRepository` or configures other persistence, the conclusion "this chain does not use sessions" may no longer hold.

### 4.3. Do not assume from the name "stateless" alone

Suppose custom code:

~~~java
.securityContext(context -> context
    .securityContextRepository(
        new HttpSessionSecurityContextRepository()))
~~~

is combined with other configurations. That can introduce saving the context into a session, depending on where the repository and authentication filters are wired. This configuration **contradicts the bearer-only stateless goal** unless there is a clear reason.

In applications with multiple `SecurityFilterChain`s, another chain can still use `HttpSessionSecurityContextRepository` to serve browser logins. That is valid if chain scopes are properly separated.

## 5. Configuring a stateless Spring Security Resource Server

Below is a configuration for a **REST API accepting bearer JWTs in headers**, not relying on form login or session cookies.

### 5.1. Gradle dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 5.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

`issuer-uri` and audience must match the Authorization Server's contract. `audiences` is supported in many modern Spring Boot versions; if your project version lacks this property, use a custom audience validator.

### 5.3. `SecurityFilterChain`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Only appropriate if the API uses a bearer header,
            // and does not authenticate using browser auto-sent cookies.
            .csrf(AbstractHttpConfigurer::disable)

            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))

            // Explicit: do not save requests into HttpSession.
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()))

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())

            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))

            .build();
    }
}
~~~

**Explanation of each part:**

- `SessionCreationPolicy.STATELESS`: Spring Security does not create an `HttpSession` to hold authentication and does not retrieve `SecurityContext` from a session.
- `NullRequestCache`: does not save blocked requests to redirect back after login. With common stateless configurations, Spring Security already handles request caching accordingly; declaring it here emphasizes the intent.
- `oauth2ResourceServer(...jwt())`: authenticates bearer JWTs per request.
- `hasAuthority(...)`: endpoint requires the scope granted by the AS.
- `anyRequest().denyAll()`: undescribed endpoints are not left open by default.
- `csrf.disable()`: **only valid in the context of this bearer-only example**; not a mandatory requirement of `STATELESS`.

Do not copy the CSRF-disabling call into an application using session cookies/Browser OAuth Login without evaluating the risks.

### 5.4. You do not necessarily have to configure `NullSecurityContextRepository` manually

Spring Security sets up the appropriate repository when applying `STATELESS` via the supported flow. In many applications, there is no need to add:

~~~java
.securityContext(context -> context
    .securityContextRepository(new NullSecurityContextRepository()))
~~~

Manual customization should only be used when there is an integration reason or you need to control a specific authentication filter. If you both override the repository and use multiple login types, you must understand which repository each filter uses and whether it saves authentication.

## 6. Stateless does not mean "no HttpSession anywhere in the application"

This is the area that causes the most confusion.

### 6.1. `HttpServletRequest#getSession()` can still create a session

The Servlet API allows:

~~~java
HttpSession session = request.getSession();
~~~

By the Servlet contract, `getSession()` gets an existing session or creates one if none exists. Therefore:

~~~java
request.getSession().setAttribute("cart", cart);
~~~

can create an `HttpSession` inside a controller, service, or filter even when the Spring Security chain is configured with `STATELESS`.

If you only want to check for an **already-existing session**:

~~~java
HttpSession session = request.getSession(false);
~~~

`getSession(false)` **does not create a new session**. It returns `null` when the request has no valid session.

### 6.2. Example of a controller accidentally creating a session

~~~java
package com.example.orders.api;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionDemoController {

    @GetMapping("/demo/create-session")
    public String createSession(HttpServletRequest request) {
        HttpSession session = request.getSession();
        session.setAttribute("demo", "created");
        return "session-created";
    }
}
~~~

**This is an intentional state-creation example**, not recommended code for a stateless API. If a request reaches this controller, a session can be created and the container may emit `Set-Cookie: JSESSIONID=...`.

In a REST Resource Server that requires creating zero HTTP sessions, avoid such logic or separate it into a dedicated web/session-oriented area.

### 6.3. Filters/libraries can also call `getSession()`

A custom servlet filter, SDK, view resolver, legacy library, or flash-message component can create a session without the developer seeing it in `SecurityConfig`.

Responsibility diagram:

~~~text
Request
  |
  +-- Spring Security STATELESS
  |      +-- does not create/read auth SecurityContext from HttpSession
  |
  +-- Other Servlet Filter
  |      +-- may call request.getSession()
  |
  +-- Spring MVC
  |      +-- may process @SessionAttributes / flash attributes
  |
  +-- Controller / service
  |      +-- may call request.getSession()
  |
  +-- Other view / library
         +-- may produce its own session or cookie
```

**You cannot deduce that the entire request is stateless from a single `.sessionCreationPolicy(STATELESS)` line.**

## 7. `RequestCache` can save requests awaiting login

In a browser application, if a user visits a private URL while unauthenticated, Spring Security can remember the original request:

~~~text
GET /reports/private
   |
   +-- Not logged in
   |
   +-- HttpSessionRequestCache saves SavedRequest
   |
   +-- Redirect to login
   |
   +-- Login succeeds
   |
   +-- Redirect back to /reports/private
~~~

`HttpSessionRequestCache` stores data in `HttpSession` when a request needs to be remembered.

In a REST API using bearer tokens, you normally do not want to redirect to a form login or save requests awaiting login. The client should receive `401` with a Bearer challenge or appropriate error, then send a valid token on the next request.

### 7.1. What does `NullRequestCache` solve?

~~~java
.requestCache(cache -> cache
    .requestCache(new NullRequestCache()))
~~~

`NullRequestCache` does not save requests and does not replay saved requests. That avoids one source of session creation tied to interactive login.

According to Spring Security documentation, common `STATELESS` configurations already prevent requests from being saved in the session. Declaring `NullRequestCache` explicitly makes the config easier to read and protects the design when customizing multiple components.

### 7.2. Do not confuse saved requests with API data caching

Spring Security's `RequestCache` is a mechanism to save **a request for post-authentication redirection**, not an HTTP response cache or business cache. A `Cache-Control` header or Redis cache does not mean `HttpSessionRequestCache` is being used.

If the system uses caching reverse proxies, CDNs, or Spring Cache, review data protection policies separately—not just `SessionCreationPolicy`.

## 8. CSRF can create state even when authentication is stateless

**`SessionCreationPolicy.STATELESS` does not automatically disable or eliminate all CSRF mechanisms.** CSRF is an independent protection layer depending on the type of credential the browser automatically sends to the server.

Spring Security Servlet supports:

- `HttpSessionCsrfTokenRepository`: stores the expected CSRF token in `HttpSession`.
- `CookieCsrfTokenRepository`: stores the token in a cookie.
- Custom repository: stores it in an application-defined store.

According to Spring Security documentation, the common default repository is **`HttpSessionCsrfTokenRepository`**. Spring Security 6 uses **deferred CSRF token loading**, so the session is not necessarily loaded or created on every GET; the session may be needed when the token is actually accessed/generated/saved.

### 8.1. Example mechanism that can create a session

An application renders an HTML form and needs a CSRF token:

~~~html
<form method="post" action="/profile/update">
  <input type="hidden" name="_csrf" value="...">
  <button type="submit">Save</button>
</form>
~~~

If the expected token is stored by `HttpSessionCsrfTokenRepository`, when generating/saving the token or processing a request with a token, a session may be used.

**Therefore, an API with `STATELESS` that still has a session-based CSRF flow enabled is not guaranteed to have no `JSESSIONID`.** You must inspect the exact `CsrfTokenRepository` and the requests that materialize the token.

### 8.2. When can CSRF be disabled?

For a pure API:

~~~text
Client explicitly sends Authorization: Bearer <access-token>
Browser does not automatically attach authentication credentials
No auto-sent session cookie/Basic authentication flow
~~~

the CSRF model is typically not like a cookie-using browser app. Disabling CSRF can be considered after evaluating all credential mechanisms.

~~~java
.csrf(AbstractHttpConfigurer::disable)
~~~

**However:** an API can be stateless with respect to `SecurityContext` yet **still vulnerable to CSRF** if bearer tokens or other credentials are sent automatically by the browser via cookies. A stateless server does not equal CSRF protection.

### 8.3. Cookie-based authentication and CSRF

If an access token is placed in an `HttpOnly` cookie, the browser typically sends the cookie automatically on same-site requests and under certain cross-site conditions per cookie attributes. You must examine **CSRF protection, `SameSite`, Origin/Referer policy, CORS, and how the cookie is used**.

Do not reason:

~~~text
JWT is in a cookie -> JWT is stateless -> no CSRF
~~~

The latter two do not imply the first. A token in a cookie can be an auto-sent credential, so its threat model differs from a bearer header explicitly attached by the client.

### 8.4. `CookieCsrfTokenRepository` is still client-side state

Switching from a session CSRF repository to a cookie repository can remove some `HttpSession` usage, but the expected CSRF token then lives in a **client-side cookie**.

That is still **state**, just stored elsewhere. Nor does it remove requirements for CSRF protection, XSS defense, or controlling how JavaScript reads the token depending on the design.

## 9. OAuth2 Login / OIDC Login usually needs temporary state

An **OAuth2/OIDC Client** has a browser flow that differs from a **Resource Server** that only receives access tokens.

For example, Authorization Code + PKCE/OIDC:

~~~text
Browser accesses application
       |
       v
Application redirects to Authorization Server
       |
       +-- save OAuth2 authorization request / state
       +-- PKCE code_verifier must be safely restored
       +-- OIDC nonce may need verification
       |
       v
User logs in at Authorization Server
       |
       v
Callback /login/oauth2/code/{registrationId}
       |
       +-- verify state/nonce per flow
       +-- obtain authorization code
       +-- exchange code for tokens
       |
       v
Establish application login state (design-dependent)
~~~

Spring Security OAuth2 Login typically uses `HttpSessionOAuth2AuthorizationRequestRepository` to store `OAuth2AuthorizationRequest` in `HttpSession` between redirect and callback.

### 9.1. Mechanically setting `STATELESS` for OAuth2 Login can break the flow

If on the same chain:

~~~java
.oauth2Login(Customizer.withDefaults())
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

still keeps a session-based authorization request repository, the redirect/callback flow may fail because temporary state is not restored or because session creation/usage conflicts with the policy.

This is not a JWT signature error, but an **architectural mismatch**: OAuth2 Login needs to retain state/PKCE/nonce, whereas a bearer-only API does not need to store login state in a session.

Common solutions:

1. **Separate `SecurityFilterChain`s**: stateless API; separate browser login/session chain.
2. Or design an **`AuthorizationRequestRepository` not backed by HTTP session**, while still protecting `state`, PKCE verifier, OIDC nonce, and replay per protocol requirements.
3. Do not disable `state`/nonce checks just to make login "work" under `STATELESS`.

### 9.2. Stateless Resource Server and OIDC Client are not the same role

One application can play both roles, but should clearly distinguish them:

| Role | Common credential | Needed state |
|---|---|---|
| Resource Server API | JWT/opaque bearer access token | Session not required to store authentication |
| Browser OIDC Client | Authorization Code/OIDC login, cookie/session or BFF | Usually needs flow state, may have session |
| Authorization Server | Issues access/refresh tokens, consent, keys | Holds extensive AS-side state |
| Backend-for-Frontend | Frontend login cookie, holds access tokens server-side | May need server-side session/token store |

Do not apply a blanket rule "all OAuth2 applications must be stateless" to every role.

## 10. Applications having both a REST API and OIDC Login

A common architecture is:

~~~text
/api/**         -> Bearer JWT Resource Server, stateless
/web/**         -> Browser OIDC Login, session/CSRF per architecture
/oauth2/**      -> OAuth2 authorization redirect
/login/**       -> OAuth2 Login callback or login page
/actuator/**    -> Separate operational policy
~~~

You can configure **two `SecurityFilterChain`s** with explicit ordering.

### 10.1. Stateless API chain

~~~java
package com.example.shop.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/assets/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

**Assumption:** this example requires the **OAuth2 Client** dependency when `oauth2Login` is enabled:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
~~~

and valid client registration/provider configuration; the code above will not automatically have working OAuth2 Login without IdP/redirect URI settings.

### 10.2. Why isn't the second chain set to `STATELESS`?

The web chain uses OAuth2 Login. Authorization request/PKCE/OIDC nonce state and login sessions may need to be preserved across redirects. You can use an appropriate default configuration or design dedicated state storage.

CSRF for the browser chain is also not disabled in the example, since the browser can use cookies.

### 10.3. With multiple chains, a session can still exist

If a browser accesses the web chain and the server creates an `HttpSession`, the `JSESSIONID` cookie may be sent on requests to `/api/**` depending on cookie path/domain and browser behavior.

That **does not prove** the API chain is using the session to restore authentication. With a proper `STATELESS` config, the API chain still requires a bearer token and does not read the security context from the session merely because a cookie exists.

**However:** you must test that the API chain is genuinely selected and that no other mechanism accepts the session cookie as a valid credential.

### 10.4. `securityMatcher` boundaries are critical

With multiple chains:

- `securityMatcher("/api/**")` decides **where the API chain applies**.
- `requestMatchers(...)` inside the chain decides HTTP authorization for requests already matched to the chain.
- `@Order` determines which chain is evaluated first.
- `anyRequest()` inside one chain does not protect requests outside its `securityMatcher` scope.

If you only define an `/api/**` chain with no fallback for the rest, unmatched URLs may fall outside Spring Security's filter chain. Ensure there is an appropriate chain or fallback policy.

## 11. Components that can create `HttpSession` or other state

The following table is useful when you see `Set-Cookie: JSESSIONID` even though the API uses `STATELESS`.

| Component/mechanism | What kind of state can it create/store? | What to check |
|---|---|---|
| Controller `request.getSession()` | `HttpSession` | Is it being used to store cart/user/flags? |
| Servlet filter/custom interceptor | `HttpSession` | Are there `getSession()` calls or session attributes? |
| `HttpSessionSecurityContextRepository` | `SecurityContext` in session | Was the stateless repo overridden? |
| `HttpSessionRequestCache` | `SavedRequest` in session | Is there a redirect/login flow or request caching? |
| `HttpSessionCsrfTokenRepository` | Expected CSRF token in session | Is a CSRF token being loaded/generated? |
| `HttpSessionOAuth2AuthorizationRequestRepository` | OAuth2 authorization request/state | Which chain handles OAuth2 Login? |
| Form login / login success handler | Auth/session/saved request per config | Is interactive login enabled? |
| Session fixation strategy | Changes session ID or migrates session on login | Is there any browser login chain? |
| Session concurrency tracking | Session registry/tracking | Is concurrent login limiting enabled? |
| Spring MVC `@SessionAttributes` | Model attributes in session | Is the MVC controller stateful? |
| `@SessionScope` bean | Bean data per session | Is the bean accessed during the request? |
| Flash attributes and redirect | Flash map retained across requests, often session-related | Is `RedirectAttributes.addFlashAttribute` used? |
| `SessionLocaleResolver` | Locale in session | What MVC locale strategy is configured? |
| JSP/view/third-party library | Session or cookie depending on tech | Does the view technology create a session? |
| Spring Session (Redis/JDBC) | Backing storage for `HttpSession` | Is a bean/filter replacing servlet session storage? |
| API gateway / reverse proxy | Other cookies, sticky routing, cache | Did the proxy or app issue the cookie? |
| JWKS/introspection cache | Cached token verification data | Not an HTTP session, yet still state |
| Rate limiter, revocation list, ACL DB | Business/security state | Not eliminated by stateless authentication |

**A row in this table does not mean the component always creates a session.** For example, deferred CSRF loading can avoid touching the session on regular GETs; `@SessionAttributes` only applies when a controller uses it; a login success handler only runs when the corresponding login occurs.

## 12. `Spring Session` and Redis do not mean every API uses stateful authentication

When a project uses Spring Session, `HttpSession` can be stored in Redis or JDBC instead of only in servlet container memory.

For example:

~~~text
Servlet request.getSession()
          |
          v
Spring Session wrapper
          |
          v
Redis / JDBC session repository
```

This allows sessions to survive across nodes and changes how metrics/cookies are observed.

However, if a stateless bearer API **does not call `getSession()` and does not save `SecurityContext`**, having Spring Session as a project dependency does not necessarily mean that API uses session authentication.

Conversely, if a controller or filter accidentally creates a session, it may write state into Redis. Checking Spring Session storage and events can help trace the origin.

**Do not solve the problem by blindly removing the Spring Session dependency** if the application also has OIDC Login or a web area that genuinely needs sessions.

## 13. What does `JSESSIONID` appearing mean?

Servlet containers typically use the `JSESSIONID` cookie to identify an `HttpSession`. A response may contain:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=F5A...; Path=/; HttpOnly; Secure
~~~

It usually indicates that a session was created or managed during request handling. However:

- `JSESSIONID` **does not by itself prove** Spring Security is storing authentication in the session.
- The cookie may have been issued by **another chain**, an earlier endpoint, or a Servlet component.
- A client may send an earlier `Cookie: JSESSIONID=...` even when the API ignores it.
- Absence of `JSESSIONID` **does not prove** the application is completely stateless: Redis, DB, JWT denylists, or other cookies may still exist.

### 13.1. Distinguishing request cookies and response cookies

Request:

~~~http
GET /api/orders HTTP/1.1
Cookie: JSESSIONID=old-session-id
Authorization: Bearer <access-token>
~~~

Response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=new-session-id; Path=/; HttpOnly
~~~

These are two different observations. A `Cookie` sent by the client may just be an old cookie; `Set-Cookie` shows a server/proxy component issuing or replacing a cookie.

To know **who created the session**, find the `getSession()` callsite or equivalent mechanism rather than just spotting the cookie.

### 13.2. `JSESSIONID` is not a bearer token

In a JWT Resource Server configured to accept only bearer headers, a `JSESSIONID` cookie cannot substitute for:

~~~http
Authorization: Bearer <access-token>
~~~

If removing the bearer header still lets the API grant access via `JSESSIONID` alone, investigate which chain is authenticating the request or whether another session/cookie mechanism is active. That may be an intentional design on a browser chain, but must be clearly separated from bearer-only APIs.

## 14. Using `getSession(false)` to observe without creating a session

A common diagnostic mistake is using:

~~~java
// Dangerous for observation: this line itself can create a session.
request.getSession().getId();
~~~

Because `getSession()` can create a session, the debugging tool **causes the very symptom being investigated**.

Use instead:

~~~java
HttpSession existing = request.getSession(false);

boolean hasSession = existing != null;
~~~

If you need to observe after all filters/controllers run, write a temporary filter using only `getSession(false)`.

### 14.1. Session observation filter for development environments

~~~java
package com.example.orders.diagnostics;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

public class SessionObservationFilter
        extends OncePerRequestFilter {

    private static final Logger log =
        LoggerFactory.getLogger(SessionObservationFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        boolean existedBefore =
            request.getSession(false) != null;

        try {
            chain.doFilter(request, response);
        } finally {
            boolean existsAfter =
                request.getSession(false) != null;

            log.debug(
                "path={} sessionBefore={} sessionAfter={}",
                request.getRequestURI(),
                existedBefore,
                existsAfter
            );
        }
    }
}
~~~

This is an **illustrative filter**. If used, register it for the right dispatcher/path/order and enable it only under appropriate dev/test/diagnostics profiles. Avoid letting a diagnostics filter collect sensitive data in production.

This filter only observes whether a session existed **before/after the scope it wraps**. An earlier filter may have already created the session before measurement, or the session may have been invalidated during processing. It **does not pinpoint the exact callsite that created the session**.

### 14.2. Finding the exact source of session creation

Investigation steps:

1. Search permitted code for calls to `getSession()`, `getSession(true)`, and `setAttribute` on sessions.
2. Check MVC features like `@SessionAttributes`, flash attributes, and session-scoped beans.
3. Check `SecurityContextRepository`, `RequestCache`, `CsrfTokenRepository`, and OAuth2 `AuthorizationRequestRepository`.
4. Check which filter chain is selected, especially in applications with multiple chains.
5. Observe session creation events or servlet-session diagnostics in a test environment.
6. Correlate `Set-Cookie` responses with access logs and the actual chain/handler.
7. Check Spring Session/Redis, proxies, or the container if the cookie does not originate from an application component.

A single `JSESSIONID` sighting is not enough to conclude the root cause.

## 15. Testing with real HTTP requests

The examples below use placeholder addresses and tokens.

### 15.1. Calling a public endpoint without cookies

~~~bash
curl -i https://api.example.com/api/public/ping
~~~

Observe:

- Does the response include `Set-Cookie: JSESSIONID`?
- Do other headers match policy?
- Did the request actually traverse the API chain?

Note that `permitAll()` is still inside the security filter chain. If a client sends an **invalid bearer token** to a public endpoint, the authentication filter may reject it before reaching authorization; therefore test sending no token separately.

### 15.2. Calling a token-protected endpoint

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/orders
~~~

With a proper stateless bearer API, a valid request can be handled without creating an `HttpSession`. **However**, seeing no cookie does not prove the entire system holds no state.

### 15.3. Testing with an old cookie

~~~bash
curl -i \
  -H "Cookie: JSESSIONID=some-old-value" \
  https://api.example.com/api/orders
~~~

If the endpoint requires a bearer token and no `Authorization` header is sent, by policy it should not authenticate using only the old cookie.

Do not paste real session IDs or access tokens into tickets/logs/chats. Both session IDs and bearer tokens can be sensitive credentials.

### 15.4. Testing two independent requests

~~~bash
curl -i https://api.example.com/api/public/ping
curl -i https://api.example.com/api/public/ping
~~~

You can use `curl` with a cookie jar in a test environment to distinguish whether the server created a session on the first call or the client sent a cookie from an earlier session, but never store a jar containing real credentials in an unsafe place.

## 16. Technical test: request does not create an `HttpSession`

A simple integration test can confirm a public endpoint does not create a session when the full request runs through Spring MVC/Security in a test environment.

Example controller:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicController {

    @GetMapping("/api/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
~~~

MockMvc:

~~~java
package com.example.orders.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class StatelessSessionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRequestDoesNotCreateSession() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(result ->
                assertNull(result.getRequest().getSession(false)));
    }
}
~~~

This test assumes the corresponding filter chain is active and the `ping` endpoint exists. `getSession(false)` in the assertion **does not create a session**, making it suitable for observation.

**Limitation:** testing one endpoint does not prove *every* request/HTTP method avoids creating a session. You must separately test code paths that trigger CSRF, login, errors, redirects, custom filters, and endpoints using MVC state.

### 16.1. Test proving the API does not trust session cookies

An important security requirement is that requests to `/api/orders` **must not be authenticated using `JSESSIONID` alone** if it is a bearer-only API.

An integration test can be designed as:

~~~text
Given a session/cookie from the browser login chain
When calling GET /api/orders with only that cookie and no Bearer header
Then the API chain returns 401 or denies access per policy
```

This test must run through the real `SecurityFilterChain`s and verify that the `/api/**` chain is selected. Do not merely mock an `Authentication` and conclude sessions are unused.

### 16.2. Authentication tests are not session tests

Spring Security Test's `SecurityMockMvcRequestPostProcessors.jwt()` creates a mock JWT authentication to test authorization. It can bypass real JWT signature/issuer validation. Its test security context mechanism may also differ from the actual bearer token flow.

Therefore, to prove "a valid bearer token request does not create a session", use an integration test with a controlled `JwtDecoder`/test key or a test harness that truly exercises the bearer authentication path, then observe sessions/cookies. Do not rely solely on `.with(jwt())` to draw conclusions about production behavior.

### 16.3. Negative tests you should have

| Scenario | Expected for a bearer-only API |
|---|---|
| Public GET without token | Permitted, no authentication session created |
| Private GET without token | 401 per bearer entry point |
| Private GET with valid JWT | Authenticated from token, no session needed |
| Private GET with `JSESSIONID` only | Not treated as authenticated unless cookie auth exists |
| Private GET with expired JWT | 401 |
| Valid JWT lacking scope | 403 |
| Another request with the same JWT | Authenticated based on the re-sent token |
| Controller accidentally calls `getSession()` | Test detects session creation |
| Session-based CSRF repository triggered | Test detects state per configuration |
| OAuth2 Login redirect/callback | Contained in web chain with appropriate state |
| API URL outside security matcher | Must not bypass protection |
| Error/forward dispatch | Does not create/accept unexpected state |

**These are suggested test cases**, not a QA/Gradle run required during lesson authoring.

## 17. Cookies, JWT, CSRF, and XSS: different concerns

Three types of clients may be encountered:

| Client | Credential typically sent | Risks to address |
|---|---|---|
| CLI/server-to-server | `Authorization: Bearer ...` | Token protection, TLS transport, validation |
| SPA sending Bearer header | Token explicitly added to header by JavaScript/code | Token theft/XSS, CORS, storage policy |
| Browser sending cookies | Cookie auto-sent by browser per attributes | CSRF, session/cookie security, SameSite |

`STATELESS` does not dictate how the **client** stores tokens. An API that does not use HTTP sessions can still receive a bearer token stored in a cookie or coexist with cookie sessions on another chain.

### 17.1. Disabling CSRF does not solve XSS

If a token is stolen by malicious JavaScript, CSRF protection will not prevent an attacker from using that token. You must combine CSP, escaping, dependency hygiene, scope restriction, and an appropriate token storage policy.

Conversely, a token in an `HttpOnly` cookie can prevent JavaScript from reading the cookie directly, but an auto-sent cookie introduces CSRF considerations. There is no single default token storage option right for every architecture.

### 17.2. CORS is not authentication

A CORS configuration restricting `Origin` only affects how **browsers** read cross-origin responses; it does not reject non-browser HTTP clients. CORS and stateless session policies are independent of bearer authentication.

If a browser SPA sends an `Authorization` header, CORS preflight may need to be handled before authentication, but never broaden business endpoint permissions just to "fix CORS."

## 18. What does logout mean for a stateless API?

With session login, logout can invalidate `HttpSession` and clear the `SecurityContext` stored inside it. With a stateless JWT bearer API:

~~~text
Client discards the token on its side
         |
         +-- Does not automatically invalidate already-issued JWTs everywhere
```

`STATELESS` does not automatically revoke access tokens.

If a JWT has not expired and the Resource Server only verifies signatures locally, an exposed bearer token can still be reused until expiration or until a revocation mechanism takes effect.

Strategies depending on your goal:

- Short access token TTL with refresh tokens managed at the AS.
- Token revocation/introspection if the token profile supports it and the API needs current status.
- Denylist or security-version check when early invalidation is required.
- Token binding/proof-of-possession if the threat model and infrastructure support it.
- Separate logout mechanism for OIDC Client/browser sessions, not confused with API bearer credentials.

**Do not build a `/logout` endpoint for JWTs and assume tokens are invalidated** if the endpoint only clears an unrelated session.

## 19. State outside `HttpSession` can still be valid

A bearer Resource Server API often has necessary state:

### 19.1. JWKS cache

When verifying JWTs via `issuer-uri`/`jwk-set-uri`, the library normally caches public keys/JWK Sets. This is **verification key** state, not a user login session.

Key rotation requires proper cache updates; stripping all caches to be "truly stateless" degrades performance and increases network dependency without improving the session model.

### 19.2. Opaque introspection cache

A Resource Server may cache introspection results to reduce latency. This cache can store active status, scopes, or roles briefly. This is security state worth managing, especially when tokens are revoked.

It is **distinct from `HttpSession`** yet still affects revocation freshness.

### 19.3. Rate limiters and replay protection

An API can use Redis to track rate limits, idempotency keys, or used nonces, even with stateless authentication. That does not directly conflict with `SessionCreationPolicy.STATELESS`.

A sensitive action may **require** server-side state to prevent double-submit/replay. Do not remove it just to label the entire system stateless.

### 19.4. Tenant/ACL authorization

A JWT with scope `orders.read` does not by itself prove access to every order. The Resource Server can query a database to verify membership/ownership. This is **business authorization state**, not session authentication.

## 20. Differences between Spring Security Servlet and WebFlux

Examples in this lesson use `HttpSecurity`, `SecurityFilterChain`, `HttpSession`, and Servlet APIs.

In Spring WebFlux:

- Uses `ServerHttpSecurity` and `SecurityWebFilterChain`.
- The web session concept is `WebSession`, not `jakarta.servlet.http.HttpSession`.
- Security context persistence uses reactive interfaces such as `ServerSecurityContextRepository`.
- Session policies/APIs differ from Servlet; do not copy the `SessionCreationPolicy` enum verbatim into WebFlux expecting equivalent behavior.

The **general mindset** remains separating authentication state, browser login state, CSRF state, and business state, but the exact configuration must match the stack.

## 21. Diagnostic matrix for unexpected `JSESSIONID`

| Symptom | Possible cause | What to inspect |
|---|---|---|
| `JSESSIONID` even on public GET | Controller/filter/MVC creates a session | `getSession()`, `@SessionAttributes`, flash attrs |
| Session appears when opening an HTML form | `HttpSessionCsrfTokenRepository` | Is the CSRF token being materialized? |
| Session when hitting `/oauth2/authorization/...` | OAuth2 Login authorization request | `HttpSessionOAuth2AuthorizationRequestRepository` |
| Session after successful form login | Session authentication / fixation strategy | Web chain vs. API chain |
| Session after 401/redirect | `HttpSessionRequestCache`/saved request | Request cache and login entry point |
| API gets a session on error responses | Error/forward/view or another filter | Error dispatch, JSP, request cache |
| Every API request creates a Redis session entry | Spring Session + component calling `getSession()` | Spring Session filters, source callsite |
| `JSESSIONID` cookie from browser but API rejects it | Cookie from older web chain | Verify API chain still requires Bearer |
| Same cookie accesses API without Bearer | API chain may accept session auth | Inspect securityMatcher/repository/filters |
| No `JSESSIONID` yet Redis/DB state exists | Introspection, caches, ACL, rate limiting | Do not confuse HTTP sessions with other state |
| After adding `.oauth2Login()` API starts redirecting | Chain mixes browser and bearer flows | Separate filter chains, entry points |
| `STATELESS` yet custom filter saves SecurityContext in session | Repository was overridden | Each filter's `SecurityContextRepository` |

**Do not try to fix this merely by stripping cookies at the reverse proxy.** If the server still creates and uses sessions, hiding `Set-Cookie` can break login/CSRF and fails to resolve the state leak. Find what creates the state first.

## 22. Misleading configurations

### 22.1. `STATELESS` with `formLogin()`

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.formLogin(Customizer.withDefaults())
~~~

This can conflict with interactive session login, saved requests, CSRF, and redirects. Do not assume all flows will behave as expected. If the system needs web login, design a dedicated appropriate chain.

### 22.2. `STATELESS` with `oauth2Login()`

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.oauth2Login(Customizer.withDefaults())
~~~

OAuth2 Login normally uses a session to store the authorization request/state and PKCE context across redirects. Merely switching to `STATELESS` does not make login protocol-compliant stateless. Design secure state storage or separate the chains.

### 22.3. `STATELESS` with `HttpSessionCsrfTokenRepository`

~~~java
.csrf(csrf -> csrf
    .csrfTokenRepository(new HttpSessionCsrfTokenRepository()))
~~~

Depending on when the CSRF token is accessed/saved, the repository may use `HttpSession`. If an API authenticates via cookies, CSRF protection may still be required; do not delete CSRF just to get rid of `JSESSIONID` without analyzing the threat model.

### 22.4. `STATELESS` with custom `HttpSessionSecurityContextRepository`

~~~java
.securityContext(context -> context
    .securityContextRepository(
        new HttpSessionSecurityContextRepository()))
~~~

This can cause authentication to be saved/read per custom behavior, contradicting the goal of not using sessions. Only do this with an explicit, verified design for sessions and filters.

### 22.5. `STATELESS` while app code still calls session

~~~java
@GetMapping("/api/me")
String me(HttpServletRequest request) {
    request.getSession().setAttribute("visited", true);
    return "ok";
}
~~~

The `getSession()` call is the direct cause creating `HttpSession`. Do not blame `BearerTokenAuthenticationFilter` when this is the actual callsite.

## 23. A design selection workflow

When building an OAuth 2.0/OIDC API:

**Step 1 — Categorize entrypoints.** Bearer-header-only APIs, browser OIDC login, BFF, admin UI, actuator, and callbacks must be evaluated separately.

**Step 2 — Identify where credentials live.** Is it an explicit client-sent Bearer header or an auto-sent cookie? Is there a session login?

**Step 3 — Choose the matching policy.** Bearer-only Resource Servers normally use `STATELESS`; browser logins normally need sessions or equivalent state storage.

**Step 4 — Check `SecurityContextRepository` and `RequestCache`.** Prevent bearer APIs from unintentionally saving security contexts or saved requests into sessions.

**Step 5 — Review CSRF policy.** Evaluate based on the browser credential model, not solely on the word stateless.

**Step 6 — Hunt for non-security session creators.** Controllers, filters, `@SessionAttributes`, flash attrs, OAuth2 Login, and Spring Session.

**Step 7 — Test the exact filter chains and request paths.** One public GET route does not prove POST or callbacks create no state.

**Step 8 — Enforce resource permissions.** `STATELESS` does not replace tenant/owner authorization.

**Step 9 — Define token lifecycle and logout.** A stateless Resource Server does not automatically revoke JWTs.

**Step 10 — Watch configuration changes.** Whenever adding web login, CSRF, or Redis, revisit the assumption that "the API uses no sessions."

## 24. Common misconceptions

**"`STATELESS` forbids the entire application from creating sessions."** False. It is a policy for how Spring Security uses `HttpSession`; it does not forbid Servlet/MVC/application code from creating sessions.

**"`NEVER` and `STATELESS` are the same."** False. `NEVER` can use an existing session; `STATELESS` does not use a session to retrieve `SecurityContext`.

**"Having an Authentication in `SecurityContextHolder` means an HttpSession exists."** False. A context can exist for request processing without being persisted across requests.

**"A request with `JSESSIONID` means the API authenticated via cookie."** Not necessarily. The cookie may remain from a web chain while the API chain still only accepts bearer tokens.

**"No cookies means the entire application has no state."** False. Caches, databases, revocation lists, or rate-limiting state may still exist.

**"`STATELESS` automatically disables CSRF."** No. CSRF is a separate mechanism; its repository may use sessions or cookies depending on configuration.

**"A stateless API is always safe from CSRF."** False if credentials are sent automatically by the browser (e.g., cookies).

**"`oauth2Login` needs no state because it uses OAuth2."** False. Authorization Code/OIDC flows typically require state/PKCE/nonce across redirects.

**"Stateless JWT means `/logout` invalidates all old JWTs."** False. Revocation/introspection/denylists or another mechanism is needed to block tokens before expiry.

**"`getSession(false)` can create a session."** False. It only fetches an existing session; `getSession()`/`getSession(true)` can create one.

**"Do not use Redis if the API is stateless."** Incorrect. Redis can be used for rate limiting, ACLs, caching, idempotency, or sessions of another web chain.

**"Just adding `.anyRequest().denyAll()` on the API chain secures the whole app."** No, if the API chain is scoped by `securityMatcher` and other URLs lack a matching chain.

**"Whenever you see `JSESSIONID`, just strip the cookie at the proxy."** Do not do this. Find what creates the session and determine which flows genuinely need it.

## 25. Self-check questions

**1.** What does `SessionCreationPolicy.STATELESS` guarantee?

> Spring Security does not create an `HttpSession` and does not use a session to obtain `SecurityContext`. It does not forbid other components from creating/storing state.

**2.** How does `NEVER` differ from `STATELESS`?

> `NEVER` does not create a session itself but may use an existing one; `STATELESS` does not use a session to restore the security context.

**3.** Why does a JWT Resource Server still have `Authentication` in a controller despite being stateless?

> `Authentication` is created for the current request from the bearer token and placed into the request's `SecurityContext`, without needing to be stored in `HttpSession`.

**4.** Can `request.getSession().setAttribute(...)` create a session in a stateless API?

> Yes. The Servlet API can create an `HttpSession` even when Spring Security uses `STATELESS`.

**5.** What should you call to check for an existing session without creating a new one?

> `request.getSession(false)`.

**6.** What state can `HttpSessionRequestCache` create?

> A `SavedRequest` in the session to resume navigation after user login. Bearer-only APIs typically do not need this mechanism.

**7.** Why can CSRF involve sessions?

> `HttpSessionCsrfTokenRepository` stores the expected CSRF token in `HttpSession` when the token is used or saved; modern Spring Security normally deferred-loads the token.

**8.** What state might an OAuth2/OIDC Login flow require?

> Authorization request, `state`, PKCE `code_verifier`, nonce, and login session depending on architecture. Do not disable these checks to force statelessness.

**9.** An API has `STATELESS` yet `JSESSIONID` still appears. Is it accurate to immediately conclude Spring Security JWT is saving authentication?

> No. You must inspect controllers/filters, CSRF, request cache, login chains, Spring MVC, or proxies before concluding.

**10.** Does stateless JWT eliminate the need for databases/Redis?

> No. Business data, ACLs, rate limits, idempotency, caches, and revocation may require their own state, which is not synonymous with an HTTP session.

**11.** Why distinguish request cookies from `Set-Cookie` responses?

> A request cookie may be an old cookie sent by the browser; `Set-Cookie` shows the server/proxy issuing or changing a cookie. The two signals do not prove the same source of state.

**12.** When an app serves both `/api/**` bearer JWTs and OIDC Login on a web UI, what is usually the sensible implementation?

> Separate `SecurityFilterChain`s by scope: stateless API and a web chain retaining the state needed for OAuth2 Login/CSRF, along with a clear fallback security policy.

## 26. References

- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): meaning of `STATELESS`, security context, request cache, session strategies, and filter versions.
- [Spring Security — SessionCreationPolicy Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/http/SessionCreationPolicy.html): the four values `ALWAYS`, `IF_REQUIRED`, `NEVER`, `STATELESS`.
- [Spring Security — Authentication Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): `SecurityContextRepository`, `HttpSessionSecurityContextRepository`, `NullSecurityContextRepository`, `SecurityContextHolderFilter`.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): bearer JWT, claim validation, and scope mapping.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and opaque authentication.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): `HttpSessionCsrfTokenRepository`, `CookieCsrfTokenRepository`, and deferred token loading.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): browser OAuth2 Login flow, authorization request, and redirect.
- [Spring Security — Advanced OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): customization of authorization request repository and login flow.
- [Spring Security — Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher`, `@Order`, and security chain scoping.
- [Spring Session Reference](https://docs.spring.io/spring-session/reference/): session storage, Redis/JDBC, and Servlet integration.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer header and authentication errors.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access tokens, Authorization Code, refresh token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC login and requirements such as nonce.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier` and `code_challenge` in Authorization Code flow.

**Conclusion:** for a Resource Server receiving bearer access tokens, `SessionCreationPolicy.STATELESS` clearly expresses that **Spring Security does not maintain authentication via `HttpSession` across requests**. Yet an `HttpSession` can still emerge from MVC, CSRF, saved requests, OAuth2 Login, or other code/libraries; and state such as JWKS caches, databases, Redis, introspection, or revocation does not vanish. To build an API that genuinely **does not depend on HTTP sessions for authentication**, inspect the entire request path, separate chains with different needs, observe using `getSession(false)`, and independently protect concerns like CSRF, resource permissions, and token lifecycles.
