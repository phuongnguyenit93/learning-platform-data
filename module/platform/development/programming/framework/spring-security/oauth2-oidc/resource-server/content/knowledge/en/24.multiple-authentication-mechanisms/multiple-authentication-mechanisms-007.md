# Multiple Filter Chains for APIs, Browsers, and Special Endpoints

A Spring Boot application may simultaneously serve a **REST API for mobile/service clients**, a **web UI for users signing in with OpenID Connect (OIDC)**, **health checks for monitoring systems**, and **partner webhooks**. These requests do not necessarily share the same authentication mechanism:

- REST APIs typically accept **OAuth 2.0 Bearer access tokens** and operate **statelessly**.
- Traditional web UIs typically use **OAuth2 Login/OIDC**, login sessions, and session cookies.
- Health/liveness endpoints may need to respond without requiring an access token.
- Webhooks may require an **HMAC signature** or mTLS rather than a user JWT.
- Internal APIs may have separate requirements for client credentials, issuer, audience, or mTLS.

In **Spring Security Servlet**, you can define **multiple `SecurityFilterChain` beans** with their own matchers and ordering. Spring Security selects **the first chain matching the request**, then applies the filters and authorization rules **of that chain alone**.

This is a powerful tool for isolating authentication mechanisms, yet also an easy source of subtle bugs: an overly broad matcher can swallow requests meant for another chain; an overly narrow matcher can miss OIDC callbacks; a route matching no chain risks **going unprotected by Spring Security**.

This lesson explains multi-chain architecture in **Spring Security OAuth 2.0/OIDC Resource Server**, how to distinguish **`securityMatcher` from `requestMatchers`**, how to configure separate chains for **JWT APIs**, **OAuth2 Login browsers**, **special endpoints**, and a **deny-all fallback**, and how to test actual responses with MockMvc.

## 1. When Are Multiple SecurityFilterChains Needed?

Suppose the Orders application has these routes:

| Path | Caller | Desired authentication method | State management |
| --- | --- | --- | --- |
| `GET /api/orders/123` | Mobile app, service-to-service | JWT access token, scope and object permission checks | Stateless |
| `POST /api/orders` | OAuth2 client calling REST API | JWT access token with `orders.write` | Stateless |
| `GET /app/orders` | User opening browser | OAuth2 Login/OIDC, session cookie after sign-in | Session when needed |
| `GET /login` | Unauthenticated browser | Login page or redirect to OIDC Provider | Browser flow |
| `GET /oauth2/authorization/corporate` | Browser starting OIDC flow | OAuth2 authorization request | Browser flow |
| `GET /login/oauth2/code/corporate` | OIDC Provider redirecting back | Authorization Code callback | Browser flow |
| `GET /status/live` | Load balancer/orchestrator | Public per health policy | No session needed |
| `POST /hooks/payments` | Payment provider | Webhook signature or mTLS | No browser session |
| `/internal/**` | Internal service | mTLS, JWT client credentials, or dedicated option | Per internal contract |

If everything is placed in one chain with `oauth2ResourceServer()`, `oauth2Login()`, and a `permitAll()` endpoint enabled together, the app might run, yet behavior becomes harder to predict:

- An unauthenticated browser might receive a **401 Bearer challenge** instead of a **302 redirect** to login.
- An API client might receive a **302 redirect to an HTML page**, breaking the REST contract.
- A broken Bearer token sent to a public endpoint might still be processed by the auth filter and return 401.
- Cookies/sessions and **CSRF** policies might get mixed with Bearer-only routes.
- A webhook marked `permitAll` without signature verification could be spoofed.

**Multiple chains isolate mechanisms**, rather than automatically stacking multiple layers of protection. Each request typically goes through **one selected chain**, not all chains.

## 2. How Does FilterChainProxy Select a Chain?

Spring Security registers a central servlet filter, usually **`DelegatingFilterProxy`** delegating to **`FilterChainProxy`**. Inside `FilterChainProxy` is an ordered list of `SecurityFilterChain` instances.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["DelegatingFilterProxy → FilterChainProxy"]
    B --> C{"Chain 1: /status/live or /status/ready?"}
    C -- "Yes" --> D["Status chain: public GET, Bearer disabled"]
    C -- "No" --> E{"Chain 2: /api/**?"}
    E -- "Yes" --> F["API chain: JWT Resource Server + stateless"]
    E -- "No" --> G{"Chain 3: app/login/oauth2/assets?"}
    G -- "Yes" --> H["Browser chain: OAuth2 Login/OIDC + session + CSRF"]
    G -- "No" --> I["Fallback chain: denyAll"]
    D --> J["Servlet / Controller if filters permit"]
    F --> J
    H --> J
    I --> K["Reject request"]
~~~

### Three Important Rules

1. **First matching chain wins.** Only when a chain **does not match** does Spring Security evaluate the next chain.
2. **No cross-chain fallback after a match.** If the API chain matches `/api/orders/123` and returns 401/403, the request **is not retried** against the browser chain.
3. **If no chain matches, the request may fall outside Spring Security's protection** (aside from other components). Therefore, include a final chain with no `securityMatcher` that applies `denyAll` or a controlled catch-all policy.

**Lower `@Order` values are evaluated first.** For example, `@Order(1)` has higher priority than `@Order(10)`. Putting an unrestricted fallback first prevents all subsequent chains from ever being selected.

### Trace of a Real Request

~~~text
GET /api/orders/123
  |
  +-- statusChain.securityMatcher: NO
  |
  +-- apiChain.securityMatcher("/api/**"): YES
  |      |
  |      +-- BearerTokenAuthenticationFilter
  |      +-- JWT validation
  |      +-- scope authorization
  |      +-- controller/service or 401/403 error
  |
  X-- browserChain NOT evaluated further
  X-- fallbackChain NOT evaluated further
~~~

**Chain selection is an HTTP-request-layer decision.** It does not verify JWT issuer, signature, or `scope` claims itself; those steps belong to authentication inside the selected chain.

## 3. Distinguishing securityMatcher and requestMatchers

The two API names look similar but play different roles.

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().denyAll());
~~~

**`securityMatcher("/api/**")`** decides **whether the entire SecurityFilterChain applies** to the request.

**`requestMatchers(...)`** inside `authorizeHttpRequests` decides **request authorization after that chain has been selected**.

| Concept | What does it ask? | When it does not match |
| --- | --- | --- |
| `http.securityMatcher(...)` | "Should the request enter this chain?" | Spring Security tries the next chain |
| `auth.requestMatchers(...)` | "Inside this chain, which rule applies?" | Tries the next rule **in the same chain** |
| `auth.anyRequest()` | "How are remaining requests **already selected by this chain** handled?" | Never transfers to another chain |
| `@Order` | "Which chain is tried first?" | Sets priority in the chain list |

### Common Mistake Example

~~~java
// Easy mistake when thinking requestMatchers selects the chain.
@Bean
@Order(1)
SecurityFilterChain overlyBroad(HttpSecurity http) throws Exception {
    return http
        // No securityMatcher => chain matches every request by default.
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/**").authenticated()
            .anyRequest().permitAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

This chain **can match every request** because no `securityMatcher` is set, preventing lower-priority browser/health chains from ever running. `.anyRequest().permitAll()` can also still let the Bearer filter process invalid tokens before authorization.

The fix is to design clear **chain matchers** and place a **final fallback**, rather than merely adding `requestMatchers` inside an all-encompassing chain.

### Watch Out for Matcher Types and Actual Paths

Matchers can inspect path, HTTP method, servlet path, dispatcher type, or specialized matcher classes. With multiple servlets, context paths, reverse proxies, rewrites, or Spring MVC path matching, verify **the exact path Spring Security observes**. Never assume external gateway URLs and internal servlet paths are identical.

In particular, `/api` is not necessarily protected as intended just because `/api/**` was configured. If an API maps the root `/api`, test the matcher and add explicit paths when needed.

## 4. Recommended Architecture for a Mixed Application

A clear separation:

~~~text
Order application (Servlet)
|
|-- statusChain @Order(1)
|     /status/live, /status/ready
|     Public GET, no bearer, no OIDC login
|
|-- apiChain @Order(2)
|     /api/**
|     OAuth 2.0 Resource Server JWT
|     stateless, no login redirect
|     scope + business authorization
|
|-- browserChain @Order(3)
|     /app, /app/**, /assets/**
|     /login, /login/**, /oauth2/**, /logout
|     OAuth2 Login/OIDC + session, CSRF
|
|-- fallbackChain @Order(100)
      All remaining requests
      denyAll (no unintended open endpoints)
~~~

Examples use **Spring Security Servlet (Spring Boot 3.x / Spring Security 6.x common APIs)**. If the project runs **Spring WebFlux**, use `SecurityWebFilterChain`, `ServerHttpSecurity`, and reactive components instead of copying `HttpSecurity` verbatim.

To avoid repetition, assume one `SecurityConfiguration` class containing four beans. The snippets below belong to that class; add appropriate imports and client registration config in your project.

## 5. Dedicated Chain for Status Endpoints

Health/liveness endpoints must sometimes answer without an OAuth2 token. A dedicated chain for **narrow** paths keeps them from being processed by the API's Bearer filter or form/OIDC login.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain statusChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/status/live", "/status/ready")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                HttpMethod.GET, "/status/live", "/status/ready")
                .permitAll()
            .anyRequest().denyAll())
        .build();
}
~~~

This example **exposes only the two GET status endpoints**. It enables neither `oauth2ResourceServer()` nor `oauth2Login()` in the status chain, so a malformed Bearer token sent to `/status/live` **is not inspected by the API chain's Bearer filter**.

The endpoints must actually be mapped to controllers/handlers in the app. A chain permitting requests does not create endpoints; if the route does not exist, the response may be 404.

### Do Not Expose All of Actuator Publicly

A dangerous mistake is:

~~~java
// DO NOT DO THIS just to open health:
.securityMatcher("/actuator/**")
.authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
~~~

This can accidentally expose metrics, environment, configuration properties, loggers, heap dumps, or other actuator endpoints if enabled.

If using Spring Boot Actuator, you can use a dedicated matcher such as `EndpointRequest` to target **only the health endpoint**, depending on version and management port. Also control the detail level exposed by health; `show-details=always` on public health can leak internal configuration.

**Management port note:** if Actuator runs on a separate port/management context, chains on the main application context may not control those endpoints as expected. Verify the security configuration **actually applied to that management context/port**.

### Liveness vs. Readiness

- **Liveness:** typically indicates only that the process is alive, without necessarily probing every dependency.
- **Readiness:** indicates whether the instance is ready to serve traffic; may reflect dependencies.

Expose only minimal required information. Health endpoints must never leak access tokens, client secrets, sensitive connection URLs, or tenant data.

## 6. REST API Chain: JWT Resource Server, Stateless

REST APIs accept Bearer access tokens and do not sign in via browser redirects. The API chain should restrict its matcher to `/api/**`, enable OAuth2 Resource Server, and enforce explicit scopes:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(2)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .cors(Customizer.withDefaults())
        .csrf(csrf -> csrf.disable())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .requestCache(cache -> cache.disable())
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                .hasAuthority("SCOPE_orders.delete")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Intentional choices:

1. `securityMatcher("/api/**")` limits the JWT filter to API routes.
2. `sessionCreationPolicy(STATELESS)` avoids using an HTTP session to identify API callers.
3. Disabling `requestCache` prevents saving API requests and redirecting after login.
4. `oauth2ResourceServer().jwt()` validates JWT Bearer access tokens.
5. `hasAuthority("SCOPE_orders.read")` corresponds to the `orders.read` scope mapped by the default `JwtGrantedAuthoritiesConverter` in standard setups.
6. `anyRequest().denyAll()` rejects unlisted API methods/routes rather than letting any authenticated token hit every endpoint.

### Invalid JWTs Must Not Grant Authorities

Payload:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

is purely descriptive data. The Resource Server must verify **signature, issuer, expiration, audience, and appropriate token type/profile** before mapping claims to authorities.

Example application configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

`issuer-uri` typically configures the decoder/JWKS and issuer check. **Do not assume audience `orders-api` is automatically checked solely via `issuer-uri` across every version/configuration.** The API needs an audience/profile validator configured per the Authorization Server contract.

**Never use a browser OIDC ID token as an API access token.** An ID token serves the client in identifying the signed-in user; the JWT Resource Server must accept only access tokens issued **for the Orders API**.

### Why Disabling CSRF on APIs Must Be Conditional

`csrf(csrf -> csrf.disable())` in this example assumes the API authenticates exclusively with a **Bearer token actively placed in the Authorization header by the client**, not cookies automatically attached by browsers.

If the API accepts a **session cookie, Basic Auth, or browser-auto-sent credentials** along any path, concluding "stateless means no CSRF needed" can be wrong. Assess CSRF risk according to the credential mechanisms **actually** accepted, not route names alone.

With an OAuth2 Resource Server API, invalid/failed authentication tokens normally return a **401 Bearer challenge**, not a redirect to an OIDC login page. Valid tokens lacking scope normally receive **403**, per the entry point/denied handler and contract.

## 7. Browser Chain: OAuth2 Login/OIDC and Sessions

Browser paths need a different policy from APIs: users may start unauthenticated, redirect to the Authorization Server for **Authorization Code + OIDC login**, and return to the app via a callback.

Common default paths:

~~~text
/login                              -- login page (default/custom)
/oauth2/authorization/corporate     -- initiates OAuth2 authorization
/login/oauth2/code/corporate        -- callback receiving authorization code
/app                                -- application page
/app/**                             -- authenticated pages
/assets/**                          -- static CSS/JS/images
/logout                             -- application logout
~~~

A browser chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(3)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher(
            "/app", "/app/**",
            "/assets/**",
            "/login", "/login/**",
            "/oauth2/**",
            "/logout")
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                "/assets/**",
                "/login",
                "/oauth2/authorization/**",
                "/login/oauth2/code/**")
                .permitAll()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .logout(Customizer.withDefaults())
        .build();
}
~~~

Differences from the API chain:

- `oauth2ResourceServer().jwt()` is not enabled in this example's browser chain.
- `oauth2Login()` handles redirects and Authorization Code/OIDC login processing.
- Sessions may be required to retain login/security context and OAuth2 authorization request state.
- **CSRF stays enabled by default** for the browser chain; never copy `csrf.disable()` from the API.
- An unauthenticated browser request to `/app/orders` normally redirects to the login flow rather than returning a Bearer token challenge.
- Static assets should be permitted appropriately, without exposing sensitive data just because of a static file extension.

### Why Must the Callback Be Included in the Browser Chain?

The OIDC Provider redirects the browser to a path such as:

~~~http
GET /login/oauth2/code/corporate?code=...&state=... HTTP/1.1
Host: shop.example.com
~~~

If `securityMatcher` matches only `/app/**` and omits `/login/oauth2/code/**`, the callback request hits the fallback chain and **never reaches the OAuth2 login filter** needed to complete the authorization code flow. The result can be 403/404, login loops, or state errors.

Similarly, the login initiation route `/oauth2/authorization/{registrationId}` must sit inside the chain that installs the OAuth2 authorization request redirect filter.

### OIDC Client Registration

Common Maven dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

And client registration config:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate
            client-id: shop-web
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          corporate:
            issuer-uri: https://auth.example.com/realms/shop
~~~

`openid` in scope enables the OIDC flow when supported by the provider. The application must register a valid redirect URI at the Authorization Server and load `client-secret` from a secret manager/environment—**never commit real secrets in source control**.

OAuth2 login normally maintains **authorization request/state** and protects the redirect flow. Never "simplify" by disabling state validation or letting clients pick arbitrary redirect URLs. Behind a reverse proxy, configure trusted forwarded headers/base URLs so redirect URIs do not get the wrong host/scheme.

### Browser Principal Differs from JWT Resource Server Principal

After OIDC login, the browser Authentication is typically `OAuth2AuthenticationToken` and the principal can be **`OidcUser`**.

In a JWT Resource Server, the Authentication is typically `JwtAuthenticationToken` and the principal is **`Jwt`**.

| Aspect | Browser OAuth2 Login/OIDC | REST API JWT Resource Server |
| --- | --- | --- |
| Initial credential | Authorization Code/OIDC redirect | Bearer access token |
| Common principal | `OidcUser` | `Jwt` |
| Common Authentication | `OAuth2AuthenticationToken` | `JwtAuthenticationToken` |
| State storage | Session/cookie when needed | Stateless |
| When unauthenticated | Redirect to login | 401 Bearer challenge |
| CSRF protection | Required when using browser cookies/sessions | Evaluate by actual credential mechanism; Bearer-only may disable |
| Permission data | OAuth2 login authorities and custom mappings | `SCOPE_...` from access token, per converter |
| ID token purpose | Authenticates user to OIDC client | **Does not** replace access token for API calls |

Do not cast a browser principal to `Jwt`, and do not treat `OidcUser` as an Authentication usable as an API access token just because both live in Spring Security.

## 8. Fallback Chain: Blocking Unclassified Endpoints

The final chain should cover all remaining requests:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(100)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        // No securityMatcher: fallback for all remaining paths.
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

**Why is this needed?** When custom `SecurityFilterChain` beans exist, do not assume Spring Boot still adds a default chain protecting everything else. A new endpoint like `/internal/admin/export` could be added by a controller without **matching the API/browser/status matchers**.

With a `denyAll` fallback, that request is rejected rather than accidentally becoming public. Without a fallback, the request could pass through the app's servlet filters **unprotected by Spring Security**.

### Fallback Must Not Precede Other Chains

If:

~~~java
@Order(1)
SecurityFilterChain fallbackChain(HttpSecurity http) {
    // No securityMatcher -> matches every request.
}
~~~

then it can **swallow every request**, preventing higher-numbered chains from ever running. Always put the fallback last with explicitly managed ordering and regression tests.

### `denyAll` Fallback Can Affect 404 Errors

A nonexistent route such as `/unexpected` may receive **403/401 or a denial response** before reaching MVC, rather than 404. This is an intentional trade-off. If an API requires 404 for unknown routes, design a dedicated error policy **without exposing protected endpoints** or leaving unmatched paths open.

## 9. Chain Prediction Table per Request

With the four chains above:

| Request | Selected chain | Typical behavior |
| --- | --- | --- |
| GET `/status/live` without token | Status | Enters status handler if mapped |
| GET `/status/live` with invalid Bearer token | Status | Token is not inspected by the API Bearer filter on this chain |
| POST `/status/live` | Status | Denied because only GET is permitted |
| GET `/api/orders/123` without token | API | 401 and Bearer challenge |
| GET `/api/orders/123` invalid JWT signature | API | 401/invalid token |
| GET `/api/orders/123` JWT with read scope | API | Enters controller; object authorization still applies |
| POST `/api/orders` JWT missing write scope | API | Typically 403 |
| GET `/app/orders` without session | Browser | Login redirect |
| GET `/app/orders` with valid OIDC session | Browser | Can enter controller |
| GET `/oauth2/authorization/corporate` | Browser | Starts authorization redirect |
| GET `/login/oauth2/code/corporate` | Browser | OAuth2 Login processes callback |
| POST `/logout` with valid CSRF and session | Browser | Logs out per config |
| GET `/foo` | Fallback | Denied |
| POST `/hooks/payments` without webhook chain | Fallback | Denied |

Exact status codes depend on custom handlers, CSRF, controller mappings, and security config. The table describes **the intent of the example architecture**, not an HTTP guarantee for all cases.

**There is no "status chain passes it on and API chain continues" mechanism.** Each row selects exactly one chain by order.

## 10. Webhook Endpoints Should Use a Dedicated Chain, Not Just permitAll

Webhooks typically use a provider-issued **HMAC signature** instead of a JWT Bearer token. A POST:

~~~http
POST /hooks/payments HTTP/1.1
Host: shop.example.com
Content-Type: application/json
X-Webhook-Timestamp: 1763164800
X-Webhook-Signature: <provider-signature>

{"event":"payment.completed","orderId":"123"}
~~~

If you only configure:

~~~java
.requestMatchers("/hooks/**").permitAll()
~~~

and the controller trusts any JSON body, an attacker can forge payment notifications.

A separated design:

~~~text
Webhook chain /hooks/**
    |
    +-- Allow only the HTTP methods the provider uses
    +-- Verify HMAC/mTLS on the real request
    +-- Check timestamp, nonce/replay, and provider identity
    +-- Establish trusted Authentication/authorization context
    +-- Controller processes event by idempotency key
~~~

Code outline as an **integration skeleton**, not a complete HMAC verifier:

~~~java
@Bean
@Order(1)
SecurityFilterChain webhookChain(
        HttpSecurity http,
        WebhookSignatureAuthenticationFilter signatureFilter)
        throws Exception {

    return http
        .securityMatcher("/hooks/payments/**")
        .csrf(csrf -> csrf.disable())
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.POST, "/hooks/payments/**")
                .authenticated()
            .anyRequest().denyAll())
        .addFilterBefore(
            signatureFilter, UsernamePasswordAuthenticationFilter.class)
        .build();
}
~~~

`WebhookSignatureAuthenticationFilter` is an **application-written custom class** that does not exist by default in Spring Security. It must **verify the signature and prevent replay before creating Authentication**; if the verifier is not implemented yet, **do not** ship this skeleton to production assuming the route is protected.

To apply the example properly, you must:

- Match the exact real webhook routes (e.g., `/hooks/payments` and `/hooks/payments/**` if both exist).
- Read **raw request body bytes** exactly per the provider's scheme; do not parse and re-serialize JSON before HMAC if the provider signs raw bytes.
- Use a provider-specific secret, compare MACs in **constant time**, validate timestamps, and prevent replay.
- Perform zero side effects before verifying the signature.
- Avoid consuming the `InputStream` before the controller without a proper request wrapper if the handler also reads the body.
- Ensure the filter is **not registered twice**—once in the servlet container and once in the Spring Security chain—if declared as a Spring bean/filter.
- Verify tenant/account mapping and idempotency for duplicate events.
- Disable CSRF only on webhook chains **that do not use browser cookies**, never on browser chains.

If the webhook chain uses `@Order(1)` as in the skeleton, reorder the other beans or use a clear order range, though because its matcher does not overlap status/API/browser, priority is less sensitive. **The fallback must still come last.**

### Warning on Registering a Filter as a Bean

In Spring Boot, a `Filter` that is both a Spring bean and added via `http.addFilterBefore(...)` can be auto-registered by the container **outside Spring Security**. That can cause the verifier to run twice or run on unintended routes. Ensure it is registered only where intended (e.g., disabling servlet auto-registration via `FilterRegistrationBean` if needed). Never confuse a servlet Filter's `@Order` with a `SecurityFilterChain`'s `@Order`.

## 11. Internal APIs: mTLS, Client Credentials, and Dedicated Issuers

Not every internal endpoint should share the same JWT policy as public APIs. For instance, `/internal/jobs/**` might require:

- mTLS with a trusted service certificate.
- An OAuth 2.0 Client Credentials access token issued specifically for the internal API.
- A dedicated issuer/audience and a scope such as `jobs.execute`.
- Network policy at ingress/mesh **alongside** application authorization.

If using a dedicated chain:

~~~text
internalChain.securityMatcher("/internal/**")
    |
    +-- Verify caller/service identity from trusted source
    +-- Check audience/resource + scope
    +-- Action-level authorization
    +-- Deny any request that fails requirements
~~~

**Do not infer "a request from a private subnet is already authenticated".** IP addresses or proxy-set mTLS headers are trustworthy only when the proxy/ingress is hardened against spoofing, the connection path is controlled, and the app never lets clients supply those headers directly.

With OAuth2 Client Credentials, the principal may represent a **machine client**, not a human user owning an order. Business policies must distinguish service identities from human identities; never set `ownerUserId = client_id` automatically.

### When Is One Chain Not Enough?

One chain may need multiple authentication methods on **the same URL** (e.g., supporting JWT issuer A/B, or JWT and opaque tokens by contract). Simply creating two `SecurityFilterChain` beans with **the same `securityMatcher("/api/**")`** will not make Spring Security "try JWT and fall back to opaque on error":

~~~text
apiJwtChain: securityMatcher("/api/**")    @Order(1)
apiOpaqueChain: securityMatcher("/api/**") @Order(2)

Every /api/** request matches the first chain.
The second chain is not an authentication fallback.
~~~

When selecting an **AuthenticationManager by token/issuer** on the same route, use an authentication manager resolver or an explicitly designed authentication strategy, check issuers against an allowlist, and never trust unverified claims to grant privileges.

**Chains partition by HTTP request matchers**, whereas **authentication strategies** verify tokens. Those are two distinct decisions.

## 12. CORS: Separating Preflight from Authentication

Suppose a browser frontend at `https://app.example.com` calls a REST API at `https://api.example.com` with:

~~~http
GET /api/orders/123 HTTP/1.1
Origin: https://app.example.com
Authorization: Bearer <access-token>
~~~

The browser may send a **CORS preflight**:

~~~http
OPTIONS /api/orders/123 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight requests usually **do not contain a Bearer token**. If the API chain enforces token presence on every request **before CORS is handled**, the browser may never send the actual GET request.

Example `CorsConfigurationSource`:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.com"));
    cors.setAllowedMethods(List.of("GET", "POST", "DELETE"));
    cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    cors.setMaxAge(1800L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

The API chain enabled `.cors(Customizer.withDefaults())` in section 6. CORS only controls **whether browsers are permitted by policy to send/read cross-origin requests**; it is **not authentication**. Non-browser clients can still send requests directly. Never use the `Origin` header as proof of identity or tenant.

If using credentialed cookies across origins, configure `allowCredentials` and an explicit list of origins, handling SameSite/CSRF properly; avoid wildcard origins with credentials.

### `permitAll(OPTIONS)` Does Not Replace CORS

Simply adding:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/api/**").permitAll()
~~~

does not automatically generate `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, or `Access-Control-Allow-Headers` response headers. Preflights must be handled by the **CORS processor** per policy.

## 13. CSRF, Cookies, and Sessions: Do Not Copy Policies Across Chains

Key differences between API and browser:

| Item | Bearer-only API | Browser OIDC login + session |
| --- | --- | --- |
| Credential | `Authorization: Bearer` access token | Session cookie after login |
| Stateful session required | Usually no | Usually yes |
| SessionCreationPolicy | `STATELESS` | `IF_REQUIRED` or equivalent browser policy |
| CSRF | Can disable when accepting only non-auto-sent Bearer tokens | **Keep CSRF protection** for form/state-changing requests |
| Request cache/login redirect | Usually disabled | May be needed to return to original URL after login |
| When credentials missing | Bearer 401 | Usually login redirect |
| Logout | Token revocation per OAuth2/AS policy, not just deleting cookies | Clear session/cookie and optionally OIDC RP-initiated logout |

**`SessionCreationPolicy.STATELESS` does not automatically make an app using cookie credentials immune to CSRF.** Examine the authentication mechanisms accepted **in that chain** and how browsers send credentials.

### Browser Logout Does Not Equal Access Token Revocation

When a user logs out of the UI:

- The local HTTP session may be invalidated.
- The OIDC Provider session may still remain unless the app supports and triggers provider logout.
- An access token already issued for the API may remain valid until `exp` or until revoked per Authorization Server policy.

Do not confuse **local session logout**, **OIDC logout**, and **OAuth2 token revocation** as the same operation.

### Browser Cookies Do Not Authenticate a JWT API Chain

In our example, browsers use sessions to sign into `/app/**`, while `/api/**` uses stateless Bearer JWTs:

~~~text
GET /app/orders
  Cookie: JSESSIONID=...
  -> browserChain -> OIDC user / session

GET /api/orders/123
  Cookie: JSESSIONID=... but no Bearer
  -> apiChain -> no JWT Authentication
  -> typically 401 Bearer challenge
~~~

**This separation is intentional.** If an architecture wants the browser to call APIs via sessions, a different explicit design is needed, such as:

- **BFF (Backend for Frontend):** browser calls session-backed endpoints in the browser chain; server calls downstream APIs with an **appropriate access token**.
- A dedicated chain for UI backend endpoints with session authentication and CSRF.
- An OAuth2 client using an authorized client/access token to call downstream APIs under user/client delegation.

**Never send an OIDC ID token as an access token to a Resource Server** just to avoid managing login sessions; audience and token purpose differ.

## 14. OAuth2 Client and Resource Server Can Coexist in One Application

A single application can simultaneously act as:

1. An **OIDC Client** to log users in via the browser.
2. A **Resource Server** to validate Bearer access tokens arriving at its REST API.
3. An **OAuth2 Client** to call a downstream API using an issued access token.

Yet their responsibilities remain distinct:

~~~text
Browser                    Order application
    |                           |
    |  OIDC login               | OAuth2 Client
    +-------------------------->|--- Authorization Code ---> AS
    |                           |
    | session cookie            |
    +-------------------------->| browserChain
                                |
Mobile / service client         |
    | Bearer access token       |
    +-------------------------->| apiChain / Resource Server
                                |
                                +-- Bearer token for downstream API
                                    (right audience/scope/delegation)
~~~

`spring-boot-starter-oauth2-client` and `spring-boot-starter-oauth2-resource-server` can coexist, but **which chain enables which mechanism** must be stated explicitly.

Some OIDC providers issue both an ID token and an access token. Spring Security OAuth2 Login uses the ID token to establish client identity; the access token may call an API **only if** issued for the right resource/audience and matching the contract. Not every OIDC login access token can call the Orders API.

## 15. Error Responses Must Differ Between API and Browser

When a request lacks authentication:

~~~text
GET /api/orders/123
  -> apiChain
  -> JWT Resource Server requires Bearer
  -> 401 + WWW-Authenticate: Bearer

GET /app/orders
  -> browserChain
  -> OAuth2 login redirect
  -> 302 Location: /login or authorization endpoint
~~~

Example HTTP response for an API:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Invalid JWT:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Valid JWT missing scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

These are typical response shapes under **RFC 6750**, not a byte-for-byte mandatory header format across every handler/version. A request with no token may receive a Bearer challenge **without an error code**; custom handlers may add `realm`, `error_description`, or a response body.

### Never Let an API Return an HTML Redirect When Clients Expect JSON

If a mobile client receives a 302 to the OIDC login page, it may follow the redirect and receive HTML while expecting JSON. That is usually a sign of **matching the wrong chain or sharing a single authentication entry point**.

Conversely, if a browser opening `/app/orders` directly receives a 401 Bearer challenge, the OIDC login experience breaks when the UI expects a redirect.

**Endpoint paths, chain matchers, entry points, and in-chain mechanisms must form a consistent contract.**

## 16. Multiple Chains Do Not Automatically Create Data/Tenant Boundaries

A valid API JWT with `SCOPE_orders.read` does not mean it can read every user's orders. Successful OIDC browser login does not mean a user can edit every resource.

Object-level policies must still be enforced:

~~~text
Authentication:
  Who is calling? Verified JWT/OIDC session/client identity?
          |
          v
Function authorization:
  Allowed to invoke read/edit/export?
          |
          v
Business authorization:
  Which tenant does the order belong to?
  Does user/client have active matching membership?
  Valid owner/manager/share/assignment permissions?
          |
          v
Repository query scoped by tenant and relationship
          |
          v
Return only authorized data
~~~

`@EnableMethodSecurity` and `@PreAuthorize` can add protection to a service called by both browser and API controllers. However:

- Authorities from JWT (`SCOPE_...`) differ from `OidcUser` authorities; shared rules must handle both or use a unified policy abstraction.
- Method security typically relies on proxies; **self-invocation** can bypass the interceptor.
- Business policies must verify resource relationships, not merely `Authentication.isAuthenticated()`.
- Client Credentials tokens represent machine clients; never assume `sub` is always a human owner.

**Chains separate authentication mechanisms; services/repositories separate data permissions.** Never use multi-chain setup as an excuse to skip object-level authorization.

## 17. Case Study: Public Endpoint Receiving an Invalid Bearer Token

This is the easiest point of confusion between `securityMatcher` and `permitAll`.

### Public Route Inside the Same API Chain

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public-info").permitAll()
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
~~~

Behavior may be:

| Request | Typical outcome |
| --- | --- |
| `GET /api/public-info` without token | Permitted by `permitAll` |
| `GET /api/public-info` with valid JWT | May be permitted by `permitAll` |
| `GET /api/public-info` with invalid/expired JWT | **May return 401 before `permitAll` is evaluated** |

Reason: the Bearer filter is installed across **the entire API chain**, not only on `requestMatchers` requiring authentication.

### Public Route in Its Own Chain Without a Bearer Filter

In our example, `/status/live` belongs to the status chain, which installs no Bearer filter. Thus a broken JWT in a header is not parsed by **the API chain's JWT filter** when the request matches the status chain.

If the product requirement is "public endpoints must succeed even when clients send a broken token", using a **separate `securityMatcher`/chain** can fit better than `permitAll` alone.

Conversely, never use this pattern to ignore invalid tokens on routes that genuinely require authentication.

## 18. Using MockMvc to Confirm Which Chain Actually Runs

Multi-chain configuration is **filter-level**, so tests must pass through `FilterChainProxy` in the real application context. Calling a controller method directly does not test chain selection.

With Spring Boot, you can use:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class MultipleSecurityChainsTest {
    @Autowired MockMvc mvc;
    @MockitoBean JwtDecoder jwtDecoder;
}
~~~

In newer Spring Test lines (e.g., Spring Framework 6.2+), `@MockitoBean` replaces `JwtDecoder` to control JWT branches explicitly. In older Spring Boot versions, use `@MockBean` per version. **Never use annotations unavailable in your project's dependencies.**

### Example API and Status Tests

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MultipleSecurityChainsTest {

    @Autowired MockMvc mvc;
    @MockitoBean JwtDecoder jwtDecoder;

    @Test
    void publicStatusDoesNotInvokeJwtDecoder() throws Exception {
        // Assumes a GET /status/live handler returning HTTP 200 exists.
        mvc.perform(get("/status/live")
                .header(HttpHeaders.AUTHORIZATION, "Bearer broken-token"))
            .andExpect(status().isOk());

        verifyNoInteractions(jwtDecoder);
    }

    @Test
    void apiWithoutBearerGets401() throws Exception {
        mvc.perform(get("/api/orders/123"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE, startsWith("Bearer")));
    }

    @Test
    void apiWithInvalidJwtGets401() throws Exception {
        when(jwtDecoder.decode("broken-token"))
            .thenThrow(new BadJwtException("Bad JWT"));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION, "Bearer broken-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("invalid_token")));
    }

    @Test
    void jwtWithoutReadScopeGets403() throws Exception {
        when(jwtDecoder.decode("token-without-scope"))
            .thenReturn(fakeJwt("token-without-scope", "profile.read"));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION, "Bearer token-without-scope"))
            .andExpect(status().isForbidden());
    }

    private static Jwt fakeJwt(String token, String scope) {
        Instant issued = Instant.parse("2026-01-01T00:00:00Z");
        return Jwt.withTokenValue(token)
            .header("alg", "RS256")
            .issuer("https://auth.example.com/realms/shop")
            .subject("user-42")
            .issuedAt(issued)
            .expiresAt(Instant.parse("2031-01-01T00:00:00Z"))
            .claim("aud", List.of("orders-api"))
            .claim("scope", scope)
            .build();
    }
}
~~~

This test verifies **HTTP request → filter selection → JWT provider/authorization → response** in a context loaded with all chains. It **does not test real signatures**, because `JwtDecoder` is mocked. `fakeJwt(...)` does not produce a valid JWS either; write separate tests using `NimbusJwtDecoder`, real test keys/JWKS, and validators to verify signature, issuer, audience, and expiration.

### Testing Unauthenticated Browser Requests

With the default browser chain and a valid test OIDC client registration:

~~~java
mvc.perform(get("/app/orders"))
    .andExpect(status().is3xxRedirection())
    .andExpect(header().string(
        HttpHeaders.LOCATION, containsString("/login")));
~~~

Expecting `/login` applies when the app uses the default login page. With a custom entry point or direct redirect to the authorization endpoint, assert **the configured redirect target** rather than hardcoding `/login`.

### Testing OIDC Callbacks Are Not Blocked by Fallback

Do not assume `GET /login/oauth2/code/corporate?code=test` will succeed on its own: a valid callback needs `state`, a saved authorization request, a token endpoint, and OIDC validation checks. You can test matcher/chain routing with dedicated config tests, then use an **OIDC test provider/stub** for the full authorization code flow.

A test merely asserting the callback returns 302 instead of 403 is insufficient to prove OIDC login security. Test state, nonce, issuer, ID token validation, and exact redirect URI.

## 19. Multi-Chain Test Matrix

| Scenario | Expectation to verify |
| --- | --- |
| GET status without token | No login/Bearer required; reaches handler |
| GET status with broken Bearer | Not inspected by API Bearer filter |
| POST to GET-only status | Denied |
| GET API without token | 401 Bearer challenge, no login redirect |
| GET API with invalid JWT | 401 `invalid_token` per standard handler |
| GET API valid JWT missing scope | 403 |
| GET API JWT with sufficient scope | Reaches controller and proceeds to object authorization |
| GET browser page without session | Redirects to login/OIDC |
| GET browser page with valid OIDC session | Allowed per browser policy |
| POST browser without CSRF token | Blocked when CSRF is enabled and applicable |
| GET OAuth2 authorization start | Enters browser chain, starts redirect |
| OIDC callback with valid state/nonce | Enters OAuth2 login filter and completes test flow |
| Browser session cookie sent to API without Bearer | Not accepted as JWT authentication |
| API CORS preflight | Handled per CORS policy without requiring Bearer token |
| POST webhook without signature | Must be rejected by webhook verification |
| GET route outside all specific matchers | Fallback `denyAll` |
| New API route without scope rule | `apiChain.anyRequest().denyAll()` denies it |
| Two chains with overlapping matchers | Earlier-ordered chain wins; second chain does not run |
| Request with path rewritten by reverse proxy | Chain matches the actual path seen at Servlet |

When testing, check **HTTP status, `Location` on redirects, `WWW-Authenticate` for Bearer**, and verify business side effects never execute when a request is denied. `@WithMockUser` or `jwt()` in Spring Security Test synthesize mock `Authentication` that alters behavior; never use them in "no token" tests.

### Why Not Use `standaloneSetup` to Prove Multiple Chains?

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new OrdersController())
    .build();
~~~

This works for unit-testing a controller, but **does not load the real `SecurityFilterChain` beans**. Use `@SpringBootTest @AutoConfigureMockMvc` or `webAppContextSetup(context).apply(springSecurity())` when testing filter selection and authentication responses.

## 20. Diagnosing Requests Hitting the Wrong Chain

| Symptom | Possible cause |
| --- | --- |
| `GET /app/orders` returns 401 Bearer instead of 302 | API chain matches too broadly, OAuth2 Login not selected, or wrong entry point |
| `GET /api/orders` returns HTML redirect | Browser/form login chain matched before API chain or shared entry point config |
| `/login/oauth2/code/corporate` returns 403 | Browser chain misses callback, fallback wins, or wrong CSRF/filter policy |
| `/oauth2/authorization/corporate` does not redirect | Missed the chain containing OAuth2 authorization filter or bad registration |
| Public status with invalid token returns 401 | Status route sits inside a chain with a Bearer filter instead of a separate public chain |
| New API route accessible without token | No chain matched; missing fallback or overly broad `permitAll` chain |
| Browser POST always 403 | Missing/invalid CSRF token or other authorization issue, not necessarily missing OAuth scope |
| CORS preflight gets 401 | CORS ordered wrongly or chain demands Bearer before preflight processing |
| Logout succeeds yet access token still calls API | Logging out session does not revoke access tokens |
| Browser cookie insufficient for `/api/**` | Stateless API chain accepts only JWT Bearer |
| Only one chain runs despite multiple beans declared | Wrong `@Order`/`securityMatcher`; an unrestricted chain sits upfront |

To observe chain selection, you can enable **controlled** debug logging:

~~~yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: DEBUG
~~~

Depending on version, logs can reveal which chain/filter handles a request. **Do not turn on unrestricted `TRACE` in production** if logs risk capturing Bearer headers, session IDs, secrets, or personal data. Use request IDs and normalized paths for troubleshooting; never log raw access tokens.

### Distinguishing Three Different Issues

~~~text
Request entered the wrong chain?
    -> check securityMatcher, @Order, actual path

Entered right chain, authentication failed?
    -> check Bearer/OIDC/Webhook mechanism, issuer, keys, callbacks

Authenticated properly, authorization failed?
    -> check scope/authorities, method security, tenant/owner policy
~~~

Never fix a **chain selection** bug by disabling JWT checks, and never fix a **missing scope** error by opening `permitAll` across the whole API.

## 21. Common Misconceptions

**"Declaring multiple SecurityFilterChains makes requests pass through all of them."**  
No. `FilterChainProxy` selects the first matching chain. There is no default stacking of multiple security chains in order.

**"`requestMatchers('/api/**')` is enough to make the API chain handle only the API."**  
No. `requestMatchers` inside `authorizeHttpRequests` applies only **after the chain has been selected**. You need `http.securityMatcher(...)` to restrict the chain itself.

**"A `denyAll` chain at the top is safe because all requests get blocked."**  
It can block login callbacks/health checks too and stop all other chains from ever running. The fallback belongs **at the end**.

**"With `permitAll('/status/live')`, the JWT decoder will never run."**  
Not if status sits in a chain with a Bearer filter and the client sends an invalid token. Only a separate chain without Bearer cleanly isolates behavior.

**"A stateless API can still use browser session cookies by default."**  
No. The API Resource Server chain in the example verifies Bearer tokens only; browser sessions belong to another chain. If you want a BFF/session API, design it explicitly.

**"OIDC Login means the browser has an access token usable for every API."**  
No. ID tokens are not access tokens; an access token must have the right audience, scope, and purpose.

**"If CSRF is disabled for the API, it should be disabled for the browser too."**  
No. Browser sessions/cookies need CSRF protection against auto-sent credentials; the chains have different models.

**"Webhooks have no token, so `permitAll` is right."**  
No. Webhooks must be verified via signatures/mTLS or an agreed mechanism; `permitAll` does not verify HMAC automatically.

**"Another issuer's JWT with the same `sub` is the same person."**  
No. JWT identity must be qualified by trusted issuer; use `(iss, sub)` and internal mapping when needed.

**"One chain per issuer with the same `/api/**` matcher makes Spring fall back automatically."**  
No. The first matching chain is chosen; use an appropriate resolver/manager when the same path supports multiple sources.

**"A token with `SCOPE_orders.read` is enough to read any order."**  
No. Owner/tenant/share checks are separate object-level authorization.

**"Without `securityMatcher`, Spring knows the chain applies only to its declared rules."**  
No. A chain without a restrictive matcher usually **matches every request**, altering ordering and protection coverage.

## 22. Safe Multi-Chain Design Process

1. **Map all routes:** API, browser, OIDC endpoints, health, webhooks, internal, and fallback; include callbacks, logout, and static assets.
2. **Choose authentication mechanisms by caller:** Bearer JWT/opaque for APIs, OAuth2 Login for browsers, HMAC/mTLS for webhooks or services per contract.
3. **Define narrow, complete `securityMatcher`s:** remember root paths, context/servlet paths, path rewrites, and OIDC callbacks.
4. **Assign `@Order` intentionally:** specialized chains first, unrestricted fallback last; resolve any overlaps.
5. **Define per-chain policies:** stateless API/no login redirect, browser session/CSRF, minimal health, webhook signature verification.
6. **Enforce authorization rules:** scopes/roles for actions and object-level policies in services/repositories.
7. **Block undeclared routes:** `anyRequest().denyAll()` in API chains where appropriate, plus a final fallback chain.
8. **Maintain token boundaries:** OIDC ID tokens sign in the client; OAuth2 access tokens call Resource Servers with the right audience/scope.
9. **Configure CORS and CSRF properly:** preflights carry no Bearer token; browser sessions must not accidentally disable CSRF.
10. **Test every chain through `FilterChainProxy`:** no token, bad token, missing scope, login redirect, callback, logout, public, webhook, and unknown routes.
11. **Verify operations:** safe chain-selection logging, 401/403/302 metrics, redirect loops, issuer outages, and config errors.
12. **Audit trust boundaries:** gateway/forwarded headers, mTLS, multiple issuers, and principal mapping; never trust client-controlled identity headers.

**Key takeaway:** Multiple `SecurityFilterChain` beans allow a Spring Security application to serve **Bearer REST APIs**, **OIDC Login browsers**, and **special endpoints** under distinct policies. However, Spring Security **picks the first matching chain rather than running every chain in sequence**. A sound design **distinguishes `securityMatcher` from `requestMatchers`, orders `@Order` deliberately, covers OIDC callbacks, keeps APIs stateless and browsers protected with CSRF/sessions, authenticates webhooks separately, includes a deny-all fallback, and tests HTTP traffic through the real filter chains**.
